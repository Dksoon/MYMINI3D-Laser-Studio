"""
High-level laser job orchestrator.
Ties together: file → polylines → EGV → USB packets → done.
"""
from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.svg_to_path      import file_to_polylines, file_to_layered_paths
from app.core.egv_writer       import polylines_to_egv, bounding_box_egv, raster_to_egv, EGVWriter
from app.core.laser_driver     import machine_manager, K40Driver
from app.core.design_transform import apply_transforms, translate_to_origin


# ─────────────────────────────────────────────────────────────────────
# Job settings
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CutSettings:
    speed_cut_mm_s:     float = 8.0
    speed_vector_mm_s:  float = 20.0
    speed_raster_mm_s:  float = 200.0
    passes:             int   = 1


@dataclass
class JobState:
    running:    bool  = False
    aborted:    bool  = False
    progress:   float = 0.0   # 0–100
    message:    str   = ""
    elapsed_s:  float = 0.0
    error:      str   = ""


# ─────────────────────────────────────────────────────────────────────
# LaserJob
# ─────────────────────────────────────────────────────────────────────

class LaserJob:
    """
    Runs one cut or trace job on a specific machine.

    on_progress(pct: float, msg: str)
    on_done(success: bool, message: str)
    """

    def __init__(
        self,
        machine_id: int,
        file_path:  str,
        settings:   CutSettings,
        trace_only: bool = False,
        mode:       str  = "cut",   # "cut" | "engrave" | "raster"
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_done:     Optional[Callable[[bool, str], None]]  = None,
    ):
        self.machine_id  = machine_id
        self.file_path   = file_path
        self.settings    = settings
        self.trace_only  = trace_only
        self.mode        = mode
        self.on_progress = on_progress
        self.on_done     = on_done
        self.state       = JobState()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ public

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def abort(self):
        self.state.aborted = True
        drv = machine_manager._drivers.get(self.machine_id)
        if drv:
            drv.abort()

    # ------------------------------------------------------------------ worker

    def _run(self):
        self.state.running  = True
        self.state.aborted  = False
        self.state.progress = 0.0
        t_start = time.time()

        def progress(pct: float, msg: str):
            self.state.progress  = pct
            self.state.elapsed_s = time.time() - t_start
            if self.on_progress:
                self.on_progress(pct, msg)

        try:
            # 1 — Parse file with layer classification
            progress(2, "Reading file…")
            layered = file_to_layered_paths(self.file_path)
            if not layered:
                raise RuntimeError("No paths found in file.")

            progress(8, f"Parsed {len(layered)} path(s)")

            # 2 — Apply machine transforms (mirror / rotate / scale)
            progress(10, "Applying transforms…")
            from app.core.database import get_session, Machine
            bed_w, bed_h = 400.0, 400.0
            mirror_x = rotate_90 = False
            x_scale = y_scale = 1.0
            if self.machine_id:
                with get_session() as s:
                    m = s.get(Machine, self.machine_id)
                    if m:
                        bed_w     = m.bed_width_mm   or 400.0
                        bed_h     = m.bed_height_mm  or 400.0
                        mirror_x  = bool(m.mirror_design)
                        rotate_90 = bool(m.rotate_design)
                        x_scale   = m.x_scale_factor or 1.0
                        y_scale   = m.y_scale_factor or 1.0

            all_polys = [lp.polyline for lp in layered]
            all_polys = apply_transforms(
                all_polys, bed_w, bed_h,
                mirror_x=mirror_x, mirror_y=False,
                rotate_90=rotate_90,
                x_scale=x_scale, y_scale=y_scale,
            )
            all_polys = translate_to_origin(all_polys)
            for lp, poly in zip(layered, all_polys):
                lp.polyline = poly

            # 3 — Build EGV for the selected mode
            progress(12, "Generating laser commands…")

            if self.trace_only:
                egv_data = bounding_box_egv(all_polys, speed_mm_s=30.0)
                progress(18, f"Trace ready ({len(egv_data):,} bytes)")

            else:
                # Filter paths matching the current mode
                target = [lp.polyline for lp in layered if lp.operation == self.mode]

                if not target:
                    # SVG has no colour coding — treat all paths as the selected mode
                    target = all_polys

                if self.mode == "raster":
                    egv_data = raster_to_egv(
                        target,
                        speed_mm_s=self.settings.speed_raster_mm_s,
                        scanline_step_mm=0.127,
                    )
                elif self.mode == "engrave":
                    egv_data = polylines_to_egv(
                        target, speed_mm_s=self.settings.speed_vector_mm_s
                    )
                else:   # "cut" (default)
                    egv_data = polylines_to_egv(
                        target, speed_mm_s=self.settings.speed_cut_mm_s
                    )

                if not egv_data:
                    raise RuntimeError(
                        f"No '{self.mode}' paths in this file.\n"
                        "SVG colour guide:  Red stroke = Cut | "
                        "Blue stroke = Engrave | Dark fill = Raster"
                    )

                mode_labels = {"cut": "Cut", "engrave": "Engrave", "raster": "Raster"}
                progress(18, f"{mode_labels.get(self.mode, self.mode)} ready "
                             f"({len(egv_data):,} bytes, {len(target)} path(s))")

            # 4 — Get driver
            drv = machine_manager._drivers.get(self.machine_id)
            if not drv or not drv.is_connected:
                raise RuntimeError(
                    "Machine is not connected.\n"
                    "Go to Machines → Connect first."
                )

            # 5 — Send (with multi-pass support)
            for pass_num in range(self.settings.passes):
                if self.state.aborted:
                    break
                pass_label = (f"Pass {pass_num+1}/{self.settings.passes} "
                              if self.settings.passes > 1 else "")

                def _progress_cb(pct: float):
                    base = 18 + (pass_num / self.settings.passes) * 80
                    span = 80 / self.settings.passes
                    progress(base + pct * span / 100,
                             f"{pass_label}Sending… {pct:.0f}%")

                drv.send_file_raw(egv_data, on_progress=_progress_cb)
                _wait_idle(drv, timeout=300)

            if self.state.aborted:
                self._finish(False, "Job cancelled.")
            else:
                progress(100, "Done")
                self._finish(True, "Completed successfully.")

        except Exception as e:
            self.state.error = str(e)
            self._finish(False, str(e))

    def _finish(self, success: bool, msg: str):
        self.state.running  = False
        self.state.progress = 100.0 if success else self.state.progress
        self.state.message  = msg
        if self.on_done:
            self.on_done(success, msg)


def _wait_idle(drv: K40Driver, timeout: float = 300.0):
    """Block until machine stops being busy or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not drv.status.busy:
            return
        time.sleep(0.2)


# ─────────────────────────────────────────────────────────────────────
# Machine control helpers (called from Control Panel)
# ─────────────────────────────────────────────────────────────────────

def cmd_home(machine_id: int):
    drv = machine_manager._drivers.get(machine_id)
    if drv and drv.is_connected:
        drv.home()


def cmd_unlock(machine_id: int):
    drv = machine_manager._drivers.get(machine_id)
    if drv and drv.is_connected:
        drv.unlock_rail()


def cmd_initialize(machine_id: int):
    drv = machine_manager._drivers.get(machine_id)
    if drv and drv.is_connected:
        drv.home()
        drv.unlock_rail()


def cmd_jog(machine_id: int, dx_mm: float, dy_mm: float, speed: float = 30.0):
    """Move head by (dx, dy) mm without firing laser."""
    from app.core.egv_writer import polylines_to_egv
    polylines = [[(0, 0), (dx_mm, dy_mm)]]
    egv = polylines_to_egv(polylines, speed_mm_s=speed, trace_only=True)
    drv = machine_manager._drivers.get(machine_id)
    if drv and drv.is_connected:
        drv.send_file_raw(egv)


def cmd_move_to(machine_id: int, x_mm: float, y_mm: float, speed: float = 30.0):
    """Move head to absolute position."""
    from app.core.egv_writer import polylines_to_egv
    drv = machine_manager._drivers.get(machine_id)
    if not drv or not drv.is_connected:
        return
    # We track position in the driver
    cx = getattr(drv, "_pos_x", 0.0)
    cy = getattr(drv, "_pos_y", 0.0)
    polylines = [[(cx, cy), (x_mm, y_mm)]]
    egv = polylines_to_egv(polylines, speed_mm_s=speed, trace_only=True)
    drv.send_file_raw(egv)
    drv._pos_x = x_mm
    drv._pos_y = y_mm


def cmd_stop(machine_id: int):
    drv = machine_manager._drivers.get(machine_id)
    if drv:
        drv.abort()
