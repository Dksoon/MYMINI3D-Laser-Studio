from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox, QFrame,
    QFileDialog, QSizePolicy, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QTransform
try:
    from PyQt6.QtSvgWidgets import QSvgWidget
    from PyQt6.QtSvg import QSvgRenderer
    SVG_AVAILABLE = True
except ImportError:
    SVG_AVAILABLE = False

from app.core.database import get_session, Machine, MachineStatus
from app.core.laser_driver import machine_manager
from app.core.laser_job import (
    LaserJob, CutSettings, cmd_home, cmd_unlock,
    cmd_initialize, cmd_jog, cmd_move_to, cmd_stop
)
from app.core.svg_to_path import file_to_polylines, file_to_layered_paths, LayeredPath


# ─────────────────────────────────────────────────────────────────────
# Bed Preview Widget
# ─────────────────────────────────────────────────────────────────────

class BedPreview(QWidget):
    """Visual preview of the laser bed with the loaded design overlaid."""

    # Colour map: operation → display colour (matches K40 Whisperer convention)
    _OP_COLORS = {
        "cut":     QColor("#ff4444"),   # red   — Vector Cut
        "engrave": QColor("#4499ff"),   # blue  — Vector Engrave
        "raster":  QColor("#8b949e"),   # grey  — Raster Engrave
    }

    def __init__(self, bed_w: float = 400.0, bed_h: float = 400.0, parent=None):
        super().__init__(parent)
        self.bed_w     = bed_w
        self.bed_h     = bed_h
        self._layered: list[LayeredPath] = []
        self._svg_path = ""
        self._head_x   = 0.0
        self._head_y   = 0.0
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#0d1117;")

    def load_file(self, file_path: str):
        self._svg_path = file_path
        try:
            self._layered = file_to_layered_paths(file_path)
        except Exception:
            self._layered = []
        self.update()

    def set_head_position(self, x: float, y: float):
        self._head_x = x
        self._head_y = y
        self.update()

    def paintEvent(self, event):
        p   = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w   = self.width()
        h   = self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor("#0d1117"))

        # Bed area
        margin  = 20
        bed_px_w = w - 2 * margin
        bed_px_h = h - 2 * margin
        scale   = min(bed_px_w / self.bed_w, bed_px_h / self.bed_h)
        off_x   = margin + (bed_px_w - self.bed_w * scale) / 2
        off_y   = margin + (bed_px_h - self.bed_h * scale) / 2

        def to_px(xmm, ymm):
            return off_x + xmm * scale, off_y + ymm * scale

        # Bed rectangle
        bx, by = to_px(0, 0)
        bw      = self.bed_w * scale
        bh      = self.bed_h * scale
        p.setPen(QPen(QColor("#30363d"), 1))
        p.setBrush(QBrush(QColor("#161b22")))
        p.drawRect(int(bx), int(by), int(bw), int(bh))

        # Grid (every 50mm)
        p.setPen(QPen(QColor("#21262d"), 1, Qt.PenStyle.DotLine))
        step_mm = 50
        x = step_mm
        while x < self.bed_w:
            px, _ = to_px(x, 0)
            p.drawLine(int(px), int(by), int(px), int(by + bh))
            x += step_mm
        y = step_mm
        while y < self.bed_h:
            _, py = to_px(0, y)
            p.drawLine(int(bx), int(py), int(bx + bw), int(py))
            y += step_mm

        # Grid labels
        p.setPen(QPen(QColor("#484f58")))
        try:
            from PyQt6.QtGui import QFont
            f = p.font(); f.setPointSize(7); p.setFont(f)
        except Exception:
            pass
        for x in range(0, int(self.bed_w) + 1, 100):
            px, _ = to_px(x, 0)
            p.drawText(int(px) - 10, int(by) - 4, f"{x}")
        for y in range(0, int(self.bed_h) + 1, 100):
            _, py = to_px(0, y)
            p.drawText(int(bx) - 30, int(py) + 4, f"{y}")

        # Draw design paths — colour coded by operation type
        # Red = Vector Cut  |  Blue = Vector Engrave  |  Grey = Raster
        if self._layered:
            for lp in self._layered:
                color = self._OP_COLORS.get(lp.operation, QColor("#f78166"))
                pen = QPen(color, 1)
                if lp.operation == "raster":
                    pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                poly = lp.polyline
                if len(poly) < 2:
                    continue
                for i in range(len(poly) - 1):
                    x1, y1 = to_px(*poly[i])
                    x2, y2 = to_px(*poly[i + 1])
                    p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Legend — bottom-left of bed
        legend = [("Cut", "#ff4444"), ("Engrave", "#4499ff"), ("Raster", "#8b949e")]
        try:
            from PyQt6.QtGui import QFont as _QF
            lf = _QF(); lf.setPointSize(7); p.setFont(lf)
        except Exception:
            pass
        lx = int(bx) + 4
        ly = int(by + bh) - 4
        for label, clr in legend:
            p.setPen(QPen(QColor(clr), 1))
            p.drawText(lx, ly, f"■ {label}")
            lx += 58

        # Head position crosshair
        hx, hy = to_px(self._head_x, self._head_y)
        p.setPen(QPen(QColor("#58a6ff"), 1))
        size = 8
        p.drawLine(int(hx - size), int(hy), int(hx + size), int(hy))
        p.drawLine(int(hx), int(hy - size), int(hx), int(hy + size))
        p.setPen(QPen(QColor("#58a6ff"), 1, Qt.PenStyle.DotLine))
        p.drawEllipse(int(hx - 4), int(hy - 4), 8, 8)

        # Origin corner mark
        ox, oy = to_px(0, 0)
        p.setPen(QPen(QColor("#3fb950"), 2))
        p.drawLine(int(ox), int(oy), int(ox) + 12, int(oy))
        p.drawLine(int(ox), int(oy), int(ox), int(oy) + 12)

        p.end()


# ─────────────────────────────────────────────────────────────────────
# Jog button grid
# ─────────────────────────────────────────────────────────────────────

_JOG_MAP = {
    (0,0): (-1,-1,"↖"), (0,1): (0,-1,"↑"), (0,2): (1,-1,"↗"),
    (1,0): (-1, 0,"←"), (1,1): (0, 0,"⊙"), (1,2): (1, 0,"→"),
    (2,0): (-1, 1,"↙"), (2,1): (0, 1,"↓"), (2,2): (1, 1,"↘"),
}

class JogPad(QWidget):
    jog_requested = pyqtSignal(float, float)  # dx_mm, dy_mm

    def __init__(self, step_spin: QDoubleSpinBox, parent=None):
        super().__init__(parent)
        self._step = step_spin
        grid = QGridLayout(self)
        grid.setSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)
        for (row, col), (dx, dy, label) in _JOG_MAP.items():
            btn = QPushButton(label)
            btn.setFixedSize(30, 30)
            btn.setObjectName("JogBtn")
            if label == "⊙":
                btn.setStyleSheet(
                    "background:#161b22; color:#484f58; border:1px solid #21262d;"
                    "border-radius:2px; font-size:10px; min-height:0; max-height:30px;"
                )
                btn.setEnabled(False)
            else:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _dx, _dy = dx, dy
                btn.clicked.connect(
                    lambda _, x=_dx, y=_dy: self.jog_requested.emit(
                        x * self._step.value(), y * self._step.value()
                    )
                )
            grid.addWidget(btn, row, col)


# ─────────────────────────────────────────────────────────────────────
# Machine Control Panel (dialog)
# ─────────────────────────────────────────────────────────────────────

class MachineControlPanel(QDialog):
    def __init__(self, machine_id: int, parent=None):
        super().__init__(parent)
        self._machine_id  = machine_id
        self._file_path   = ""
        self._polylines   = []
        self._active_job: Optional[LaserJob] = None
        self._head_x      = 0.0
        self._head_y      = 0.0

        with get_session() as s:
            m = s.get(Machine, machine_id)
            self._machine_name = m.name if m else f"Machine {machine_id}"
            self._bed_w = m.bed_width_mm  if m else 400.0
            self._bed_h = m.bed_height_mm if m else 400.0

        self.setWindowTitle(f"Control — {self._machine_name}")
        self.setMinimumSize(820, 620)
        self.setWindowFlag(Qt.WindowType.Window)   # independent window, non-modal
        self._build()

        # Refresh status every 2s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(2000)

    # ------------------------------------------------------------------ build

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left control panel ────────────────────────────────────────
        left = QWidget()
        left.setStyleSheet("background:#010409; border-right:1px solid #21262d;")
        left.setFixedWidth(230)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 14, 12, 10)
        lv.setSpacing(8)

        # Machine name + status
        name_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color:#6e7681; font-size:14px;")
        name_row.addWidget(self._status_dot)
        name_lbl = QLabel(self._machine_name)
        name_lbl.setStyleSheet("font-weight:bold; color:#e6edf3; font-size:13px;")
        name_row.addWidget(name_lbl, 1)
        self._status_badge = QLabel("OFFLINE")
        self._status_badge.setObjectName("BadgeRed")
        name_row.addWidget(self._status_badge)
        lv.addLayout(name_row)

        lv.addWidget(self._divider())

        # Initialize
        init_btn = self._big_btn("Initialize Laser Cutter", "#1f6feb")
        init_btn.clicked.connect(self._initialize)
        lv.addWidget(init_btn)

        # Open / Reload file
        file_row = QHBoxLayout(); file_row.setSpacing(6)
        open_btn = QPushButton("Open File")
        open_btn.clicked.connect(self._open_file)
        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self._reload_file)
        file_row.addWidget(open_btn, 2); file_row.addWidget(reload_btn, 1)
        lv.addLayout(file_row)

        self._file_lbl = QLabel("No file loaded")
        self._file_lbl.setStyleSheet("color:#6e7681; font-size:10px;")
        self._file_lbl.setWordWrap(True)
        lv.addWidget(self._file_lbl)

        lv.addWidget(self._divider())

        # Position controls
        pos_lbl = QLabel("POSITION CONTROLS")
        pos_lbl.setObjectName("SectionLabel")
        lv.addWidget(pos_lbl)

        pos_row = QHBoxLayout(); pos_row.setSpacing(6)
        home_btn   = QPushButton("Home")
        home_btn.clicked.connect(lambda: cmd_home(self._machine_id))
        unlock_btn = QPushButton("Unlock Rail")
        unlock_btn.clicked.connect(lambda: cmd_unlock(self._machine_id))
        pos_row.addWidget(home_btn); pos_row.addWidget(unlock_btn)
        lv.addLayout(pos_row)

        # Jog step
        step_row = QHBoxLayout(); step_row.setSpacing(6)
        step_row.addWidget(QLabel("Jog Step:"))
        self._step_spin = QDoubleSpinBox()
        self._step_spin.setRange(0.1, 100); self._step_spin.setValue(10.0)
        self._step_spin.setSuffix(" mm"); self._step_spin.setFixedWidth(90)
        step_row.addWidget(self._step_spin)
        lv.addLayout(step_row)

        # Jog pad
        self._jog_pad = JogPad(self._step_spin)
        self._jog_pad.jog_requested.connect(self._do_jog)
        lv.addWidget(self._jog_pad, 0, Qt.AlignmentFlag.AlignHCenter)

        # Move To
        move_lbl = QLabel("MOVE TO")
        move_lbl.setObjectName("SectionLabel")
        lv.addWidget(move_lbl)

        xy_row = QHBoxLayout(); xy_row.setSpacing(4)
        xy_row.addWidget(QLabel("X"))
        self._move_x = QDoubleSpinBox()
        self._move_x.setRange(0, self._bed_w); self._move_x.setSuffix(" mm")
        self._move_x.setFixedWidth(80)
        xy_row.addWidget(self._move_x)
        xy_row.addWidget(QLabel("Y"))
        self._move_y = QDoubleSpinBox()
        self._move_y.setRange(0, self._bed_h); self._move_y.setSuffix(" mm")
        self._move_y.setFixedWidth(80)
        xy_row.addWidget(self._move_y)
        lv.addLayout(xy_row)

        move_btn = QPushButton("Move To")
        move_btn.clicked.connect(self._do_move_to)
        lv.addWidget(move_btn)

        lv.addWidget(self._divider())

        # Speed settings
        spd_lbl = QLabel("SPEED SETTINGS")
        spd_lbl.setObjectName("SectionLabel")
        lv.addWidget(spd_lbl)

        def _speed_row(label, default):
            r = QHBoxLayout(); r.setSpacing(4)
            l = QLabel(label); l.setStyleSheet("color:#8b949e; font-size:11px;")
            l.setFixedWidth(90)
            r.addWidget(l)
            sp = QDoubleSpinBox()
            sp.setRange(1, 500); sp.setValue(default); sp.setSuffix(" mm/s")
            r.addWidget(sp, 1)
            lv.addLayout(r)
            return sp

        self._spd_raster  = _speed_row("Raster Engrave", 200)
        self._spd_vector  = _speed_row("Vector Engrave", 20)
        self._spd_cut     = _speed_row("Vector Cut",     8)

        # Passes
        pass_row = QHBoxLayout(); pass_row.setSpacing(4)
        pass_row.addWidget(QLabel("Passes:"))
        self._passes_spin = QSpinBox()
        self._passes_spin.setRange(1, 10); self._passes_spin.setValue(1)
        pass_row.addWidget(self._passes_spin)
        pass_row.addStretch()
        lv.addLayout(pass_row)

        lv.addWidget(self._divider())

        # Trace + Cut
        trace_btn = QPushButton("◻  Trace Outline")
        trace_btn.setToolTip("Move laser along bounding box without firing — check alignment")
        trace_btn.setFixedHeight(34)
        trace_btn.setStyleSheet(
            "background:#1a2e4a; color:#58a6ff; border:1px solid #1f6feb;"
            "border-radius:6px; font-weight:bold;"
        )
        trace_btn.clicked.connect(self._do_trace)
        lv.addWidget(trace_btn)

        cut_btn = self._big_btn("▶  Start Cut", "#238636")
        cut_btn.clicked.connect(self._do_cut)
        lv.addWidget(cut_btn)

        lv.addSpacing(4)

        # STOP
        stop_btn = QPushButton("■  STOP")
        stop_btn.setFixedHeight(44)
        stop_btn.setStyleSheet(
            "background:#b62324; color:#ffffff; border:1px solid #f85149;"
            "border-radius:6px; font-size:15px; font-weight:bold;"
        )
        stop_btn.clicked.connect(self._do_stop)
        lv.addWidget(stop_btn)

        lv.addStretch()

        root.addWidget(left)

        # ── Right: preview + status ───────────────────────────────────
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        # Preview
        self._preview = BedPreview(self._bed_w, self._bed_h)
        right.addWidget(self._preview, 1)

        # Progress bar (hidden when idle)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        right.addWidget(self._progress)

        # Status bar
        status_bar = QWidget()
        status_bar.setStyleSheet(
            "background:#010409; border-top:1px solid #21262d;"
        )
        sb_lay = QHBoxLayout(status_bar)
        sb_lay.setContentsMargins(16, 6, 16, 6)
        sb_lay.setSpacing(20)

        self._pos_lbl = QLabel("Position:  X = 0.00 mm   Y = 0.00 mm")
        self._pos_lbl.setStyleSheet("color:#8b949e; font-size:11px; font-family:Consolas,monospace;")
        sb_lay.addWidget(self._pos_lbl)

        self._file_status_lbl = QLabel("No file loaded")
        self._file_status_lbl.setStyleSheet("color:#6e7681; font-size:11px;")
        sb_lay.addWidget(self._file_status_lbl)

        sb_lay.addStretch()

        self._job_status_lbl = QLabel("IDLE")
        self._job_status_lbl.setStyleSheet("color:#3fb950; font-size:11px; font-weight:bold;")
        sb_lay.addWidget(self._job_status_lbl)

        right.addWidget(status_bar)

        right_widget = QWidget()
        right_widget.setLayout(right)
        root.addWidget(right_widget, 1)

    # ------------------------------------------------------------------ helpers

    def _divider(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("background:#21262d; max-height:1px; margin:2px 0;")
        return f

    def _big_btn(self, label: str, color: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(36)
        btn.setStyleSheet(
            f"background:{color}; color:#ffffff; border:none;"
            f"border-radius:6px; font-weight:bold;"
        )
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # ------------------------------------------------------------------ status

    def _refresh_status(self):
        drv = machine_manager.status(self._machine_id)
        connected = drv.connected

        dot_color = "#3fb950" if connected else "#6e7681"
        self._status_dot.setStyleSheet(f"color:{dot_color}; font-size:14px;")

        badge_txt = "IDLE" if connected and not drv.busy else \
                    "BUSY" if connected and drv.busy else "OFFLINE"
        badge_obj = "BadgeGreen" if badge_txt == "IDLE" else \
                    "BadgeYellow" if badge_txt == "BUSY" else "BadgeRed"
        self._status_badge.setText(badge_txt)
        self._status_badge.setObjectName(badge_obj)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        self._job_status_lbl.setText(badge_txt)
        color = "#3fb950" if badge_txt=="IDLE" else "#d29922" if badge_txt=="BUSY" else "#f85149"
        self._job_status_lbl.setStyleSheet(f"color:{color}; font-size:11px; font-weight:bold;")

        # Head position
        drv_obj = machine_manager._drivers.get(self._machine_id)
        if drv_obj:
            x = getattr(drv_obj, "_pos_x", 0.0)
            y = getattr(drv_obj, "_pos_y", 0.0)
            self._pos_lbl.setText(
                f"Position:  X = {x:7.2f} mm   Y = {y:7.2f} mm"
            )
            self._preview.set_head_position(x, y)

        # Progress bar
        if drv.busy:
            self._progress.setVisible(True)
            self._progress.setValue(int(drv.progress))
        else:
            self._progress.setVisible(False)

    # ------------------------------------------------------------------ file

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Design File",
            str(Path.home()),
            "Design Files (*.svg *.dxf);;SVG (*.svg);;DXF (*.dxf)"
        )
        if path:
            self._load_file(path)

    def _reload_file(self):
        if self._file_path:
            self._load_file(self._file_path)

    def _load_file(self, path: str):
        self._file_path = path
        fname = Path(path).name
        self._file_lbl.setText(fname)
        self._file_status_lbl.setText(f"File: {fname}")
        self._preview.load_file(path)

    # ------------------------------------------------------------------ machine commands

    def _initialize(self):
        if not self._check_connected(): return
        cmd_initialize(self._machine_id)

    def _do_jog(self, dx: float, dy: float):
        if not self._check_connected(): return
        cmd_jog(self._machine_id, dx, dy)
        drv = machine_manager._drivers.get(self._machine_id)
        if drv:
            drv._pos_x = getattr(drv, "_pos_x", 0.0) + dx
            drv._pos_y = getattr(drv, "_pos_y", 0.0) + dy

    def _do_move_to(self):
        if not self._check_connected(): return
        cmd_move_to(self._machine_id, self._move_x.value(), self._move_y.value())

    def _do_trace(self):
        if not self._check_connected(): return
        if not self._file_path:
            QMessageBox.information(self, "No File", "Open a design file first.")
            return
        self._run_job(trace_only=True)

    def _do_cut(self):
        if not self._check_connected(): return
        if not self._file_path:
            QMessageBox.information(self, "No File", "Open a design file first.")
            return
        reply = QMessageBox.question(
            self, "Start Cut",
            f"Cut file:  {Path(self._file_path).name}\n\n"
            f"Speed: {self._spd_cut.value()} mm/s   "
            f"Passes: {self._passes_spin.value()}\n\n"
            "Is material loaded and the cover closed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_job(trace_only=False)

    def _do_stop(self):
        cmd_stop(self._machine_id)
        if self._active_job:
            self._active_job.abort()
        self._job_status_lbl.setText("STOPPED")
        self._job_status_lbl.setStyleSheet("color:#f85149; font-size:11px; font-weight:bold;")

    def _run_job(self, trace_only: bool):
        settings = CutSettings(
            speed_cut_mm_s    = self._spd_cut.value(),
            speed_vector_mm_s = self._spd_vector.value(),
            speed_raster_mm_s = self._spd_raster.value(),
            passes            = self._passes_spin.value(),
        )
        label = "Tracing…" if trace_only else "Cutting…"
        self._job_status_lbl.setText(label)
        self._job_status_lbl.setStyleSheet("color:#d29922; font-size:11px; font-weight:bold;")
        self._progress.setVisible(True)
        self._progress.setValue(0)

        def _progress(pct, msg):
            self._progress.setValue(int(pct))
            self._job_status_lbl.setText(msg[:30])

        def _done(ok, msg):
            self._progress.setVisible(False)
            self._progress.setValue(0)
            color = "#3fb950" if ok else "#f85149"
            self._job_status_lbl.setStyleSheet(
                f"color:{color}; font-size:11px; font-weight:bold;"
            )
            self._job_status_lbl.setText("Done" if ok else "Error")
            if not ok:
                QTimer.singleShot(0, lambda: QMessageBox.warning(
                    self, "Job Error", msg
                ))

        job = LaserJob(
            machine_id   = self._machine_id,
            file_path    = self._file_path,
            settings     = settings,
            trace_only   = trace_only,
            on_progress  = _progress,
            on_done      = _done,
        )
        self._active_job = job
        job.start()

    def _check_connected(self) -> bool:
        drv = machine_manager.status(self._machine_id)
        if not drv.connected:
            QMessageBox.warning(
                self, "Not Connected",
                "This machine is not connected.\n\n"
                "Go to Machines → Connect first."
            )
            return False
        return True

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
