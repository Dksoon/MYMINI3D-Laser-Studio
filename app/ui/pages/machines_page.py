from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSplitter, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox,
    QProgressBar, QSizePolicy, QTabWidget, QDialog
)
from PyQt6.QtCore import Qt, QTimer

from app.core.database import (
    get_session, Machine, MachineStatus,
    JobSheet, JobSheetStatus, JobItem
)
from app.core.laser_driver import machine_manager
from app.core.laser_job import (
    LaserJob, CutSettings,
    cmd_home, cmd_unlock, cmd_initialize, cmd_jog, cmd_move_to, cmd_stop
)
from app.ui.pages.machine_control_page import BedPreview, JogPad
from app.ui.dialogs.machine_dialog import MachineDialog
from app.ui.dialogs.driver_install_dialog import DriverInstallDialog

# Patch QWidget.also() helper used for inline label styling
from PyQt6.QtWidgets import QWidget as _QW
if not hasattr(_QW, "also"):
    def _also(self, fn):
        fn(self); return self
    _QW.also = _also


# ─────────────────────────────────────────────────────────────────────
# Panel helpers
# ─────────────────────────────────────────────────────────────────────

def _divider() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background:#21262d; max-height:1px; margin:4px 0;")
    return f

def _section(text: str) -> QLabel:
    l = QLabel(text.upper()); l.setObjectName("SectionLabel")
    return l

def _btn(label: str, color: str = "", fixed_h: int = 32) -> QPushButton:
    b = QPushButton(label); b.setFixedHeight(fixed_h)
    if color:
        b.setStyleSheet(
            f"background:{color}; color:#fff; border:none;"
            f"border-radius:6px; font-weight:bold;"
        )
    return b


# ─────────────────────────────────────────────────────────────────────
# Panel 1 — Machine List
# ─────────────────────────────────────────────────────────────────────

class MachineListPanel(QWidget):
    """Collapsible machine list — click ◀ to collapse to a 28px strip."""

    EXPANDED_W = 155
    COLLAPSED_W = 28

    def __init__(self, on_select, parent=None):
        super().__init__(parent)
        self._on_select  = on_select
        self._expanded   = True
        self.setFixedWidth(self.EXPANDED_W)
        self.setStyleSheet("background:#010409; border-right:1px solid #21262d;")
        self._build()

    def _build(self):
        self._main_lay = QVBoxLayout(self)
        self._main_lay.setContentsMargins(0, 0, 0, 0)
        self._main_lay.setSpacing(0)

        # Header row with collapse toggle
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(10, 8, 4, 6)
        hdr_row.setSpacing(0)
        self._hdr_lbl = QLabel("MACHINES")
        self._hdr_lbl.setObjectName("SectionLabel")
        hdr_row.addWidget(self._hdr_lbl, 1)
        self._toggle_btn = QPushButton("◀")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet(
            "background:transparent; color:#6e7681; border:none;"
            "font-size:10px; padding:0;"
        )
        self._toggle_btn.setToolTip("Collapse machine list")
        self._toggle_btn.clicked.connect(self._toggle)
        hdr_row.addWidget(self._toggle_btn)
        self._main_lay.addLayout(hdr_row)

        # Machine list
        self._list = QListWidget()
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setStyleSheet("""
            QListWidget { background:#010409; border:none; }
            QListWidget::item { padding:8px 10px; color:#8b949e;
                                border-bottom:1px solid #21262d;
                                font-size:12px; }
            QListWidget::item:selected { background:#21262d; color:#e6edf3; }
            QListWidget::item:hover    { background:#161b22; }
        """)
        self._list.currentRowChanged.connect(self._on_row)
        self._main_lay.addWidget(self._list, 1)

        self._main_lay.addWidget(_divider())

        add_btn = QPushButton("+ Add Machine")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet(
            "background:#238636; color:#fff; border:none;"
            "border-radius:0; font-weight:bold; font-size:11px; margin:0;"
            "min-height:0; max-height:28px;"
        )
        add_btn.clicked.connect(self._add)
        self._main_lay.addWidget(add_btn)

        drv_btn = QPushButton("Install Driver")
        drv_btn.setFixedHeight(22)
        drv_btn.setStyleSheet(
            "background:#010409; color:#6e7681; border:none;"
            "font-size:10px; margin:0; min-height:0; max-height:22px;"
        )
        drv_btn.clicked.connect(self._install_driver)
        self._main_lay.addWidget(drv_btn)

        # Collapsed strip — dots only, hidden by default
        self._strip = QWidget()
        self._strip.setVisible(False)
        self._strip.setStyleSheet("background:#010409;")
        strip_lay = QVBoxLayout(self._strip)
        strip_lay.setContentsMargins(0, 8, 0, 8)
        strip_lay.setSpacing(6)
        expand_btn = QPushButton("▶")
        expand_btn.setFixedSize(28, 20)
        expand_btn.setStyleSheet(
            "background:transparent; color:#58a6ff; border:none;"
            "font-size:10px; padding:0;"
        )
        expand_btn.setToolTip("Expand machine list")
        expand_btn.clicked.connect(self._toggle)
        strip_lay.addWidget(expand_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self._dot_strip_lay = strip_lay   # dots added dynamically
        strip_lay.addStretch()

        self._main_lay.addWidget(self._strip)

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.setFixedWidth(self.EXPANDED_W)
            self._list.setVisible(True)
            self._hdr_lbl.setVisible(True)
            self._toggle_btn.setVisible(True)
            self._strip.setVisible(False)
            # Restore bottom buttons
            for i in range(self._main_lay.count()):
                w = self._main_lay.itemAt(i)
                if w and w.widget():
                    w.widget().setVisible(True)
            self._strip.setVisible(False)
        else:
            self.setFixedWidth(self.COLLAPSED_W)
            # Hide everything except the strip
            for i in range(self._main_lay.count()):
                item = self._main_lay.itemAt(i)
                if item and item.widget() and item.widget() is not self._strip:
                    item.widget().setVisible(False)
                if item and item.layout():
                    pass  # header row layout — handled via widgets
            self._hdr_lbl.setVisible(False)
            self._toggle_btn.setVisible(False)
            self._list.setVisible(False)
            self._strip.setVisible(True)

    def refresh(self, selected_id: Optional[int] = None):
        self._list.clear()
        with get_session() as s:
            machines = s.query(Machine).order_by(Machine.id).all()
        for m in machines:
            drv   = machine_manager.status(m.id)
            dot   = "[+]" if drv.connected and not drv.busy else \
                    "[~]" if drv.connected and drv.busy else "[ ]"
            label = f"{dot}  {m.name}"
            item  = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            self._list.addItem(item)
            if m.id == selected_id:
                self._list.setCurrentItem(item)

    def _on_row(self, row: int):
        item = self._list.item(row)
        if item:
            self._on_select(item.data(Qt.ItemDataRole.UserRole))

    def _add(self):
        dlg = MachineDialog(self)
        if dlg.exec():
            self.refresh()

    def _install_driver(self):
        DriverInstallDialog(self).exec()


# ─────────────────────────────────────────────────────────────────────
# Panel 2 — Control Panel
# ─────────────────────────────────────────────────────────────────────

class ControlPanel(QWidget):

    W = 260   # fixed panel width — 30% wider than original 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._machine_id: Optional[int] = None
        self._file_path   = ""
        self._active_job: Optional[LaserJob] = None
        self.setFixedWidth(self.W)
        self.setStyleSheet("background:#0d1117; border-right:1px solid #21262d;")
        self._build()

    # ── tiny helpers ──────────────────────────────────────────────────
    def _B(self, txt, h=24, color="", bold=False) -> QPushButton:
        """Single button with consistent compact style."""
        b = QPushButton(txt)
        b.setFixedHeight(h)
        bg     = color if color else "#21262d"
        fg     = "#ffffff" if color else "#e6edf3"
        border = "#30363d"   # always a valid hex — no more #0 bug
        b.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border};"
            f"border-radius:3px; font-size:11px;"
            f"{'font-weight:bold;' if bold else ''}"
            f"min-height:0; max-height:{h}px;"
        )
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _row2(self, a: QWidget, b: QWidget) -> QHBoxLayout:
        """Two equal-width widgets side by side."""
        r = QHBoxLayout(); r.setSpacing(3); r.setContentsMargins(0,0,0,0)
        r.addWidget(a, 1); r.addWidget(b, 1)
        return r

    def _lbl(self, txt, size=11, color="#8b949e") -> QLabel:
        l = QLabel(txt)
        l.setStyleSheet(f"color:{color}; font-size:{size}px;"
                        "background:transparent; border:none;")
        return l

    def _spin(self, lo, hi, val, h=22, w=None, suffix="") -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi); s.setValue(val); s.setFixedHeight(h)
        if w: s.setFixedWidth(w)
        if suffix: s.setSuffix(suffix)
        s.setStyleSheet("font-size:11px;")
        return s

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        inner.setFixedWidth(self.W - 2)   # -2 for border
        inner.setStyleSheet("background:#0d1117;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        # ── Status + connect ──────────────────────────────────────────
        sr = QHBoxLayout(); sr.setSpacing(4); sr.setContentsMargins(0,0,0,0)
        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(14)
        self._status_dot.setStyleSheet("color:#6e7681; font-size:12px; border:none;")
        sr.addWidget(self._status_dot)
        self._name_lbl = QLabel("No machine selected")
        self._name_lbl.setStyleSheet(
            "color:#e6edf3; font-size:11px; font-weight:bold; border:none;"
        )
        sr.addWidget(self._name_lbl, 1)
        lay.addLayout(sr)

        conn_btns = QHBoxLayout(); conn_btns.setSpacing(3); conn_btns.setContentsMargins(0,0,0,0)
        self._conn_btn = self._B("Connect", 22, "#1f6feb", True)
        self._conn_btn.clicked.connect(self._toggle_connect)
        conn_btns.addWidget(self._conn_btn, 1)

        self._settings_btn = self._B("Settings", 22)
        self._settings_btn.clicked.connect(self._open_settings)
        conn_btns.addWidget(self._settings_btn)
        lay.addLayout(conn_btns)

        lay.addWidget(_divider())

        # ── Initialize ────────────────────────────────────────────────
        ini = self._B("Initialize Laser Cutter", 24, "#1f6feb", True)
        ini.clicked.connect(self._initialize)
        lay.addWidget(ini)

        # ── Open / Reload ─────────────────────────────────────────────
        ob = self._B("Open File",   22); ob.clicked.connect(self._open_file)
        rb = self._B("Reload File", 22); rb.clicked.connect(self._reload_file)
        lay.addLayout(self._row2(ob, rb))

        self._file_lbl = QLabel("No file loaded")
        self._file_lbl.setStyleSheet(
            "color:#6e7681; font-size:10px; border:none; background:transparent;"
        )
        self._file_lbl.setWordWrap(True)
        lay.addWidget(self._file_lbl)

        lay.addWidget(_divider())

        # ── Position Controls ─────────────────────────────────────────
        lay.addWidget(self._lbl("Position Controls:"))

        hb = self._B("Home",        22); hb.clicked.connect(lambda: self._cmd(cmd_home))
        ub = self._B("Unlock Rail", 22); ub.clicked.connect(lambda: self._cmd(cmd_unlock))
        lay.addLayout(self._row2(hb, ub))

        # Jog Step — label + spinbox on same row
        jsr = QHBoxLayout(); jsr.setSpacing(4); jsr.setContentsMargins(0,0,0,0)
        jsr.addWidget(self._lbl("Jog Step"))
        self._step = self._spin(0.1, 100, 10, 22, suffix=" mm")
        self._step.setDecimals(1)
        jsr.addWidget(self._step, 1)
        lay.addLayout(jsr)

        # ── Jog grid — K40W style ─────────────────────────────────────────
        # Unicode U+2190-2193 (← ↑ → ↓) are in every Windows font.
        # U+2022 bullet (•) for diagonal corners — clearly visible.
        # Do NOT use < > ^ v — Qt treats < > as HTML, ^ v are too small.
        JOG = {
            (0,0):(-1,-1,"•"), (0,1):(0,-1,"↑"),  (0,2):(1,-1,"•"),
            (1,0):(-1, 0,"←"), (1,1):(0, 0,""),        (1,2):(1, 0,"→"),
            (2,0):(-1, 1,"•"), (2,1):(0, 1,"↓"),  (2,2):(1, 1,"•"),
        }

        jog_wrap = QWidget()
        jog_wrap.setFixedSize(104, 104)
        jog_wrap.setStyleSheet("background:#0d1117;")
        grid = QGridLayout(jog_wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)

        from PyQt6.QtGui import QFont
        arrow_font = QFont("Segoe UI", 13)    # Segoe UI has all these glyphs
        dot_font   = QFont("Segoe UI", 10)

        for (r, c), (dx, dy, lbl) in JOG.items():
            btn = QPushButton(lbl)
            btn.setFixedSize(32, 32)

            if lbl == "":          # centre — disabled
                btn.setFont(dot_font)
                btn.setStyleSheet(
                    "background:#161b22; color:#484f58; border:1px solid #21262d;"
                    "border-radius:3px; min-height:0;"
                )
                btn.setEnabled(False)

            elif lbl == "•":  # diagonal bullet dot
                btn.setFont(dot_font)
                btn.setStyleSheet(
                    "background:#21262d; color:#8b949e; border:1px solid #484f58;"
                    "border-radius:3px; min-height:0;"
                )
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _dx, _dy = dx, dy
                btn.clicked.connect(
                    lambda _, x=_dx, y=_dy: self._do_jog(
                        x * self._step.value(), y * self._step.value()
                    )
                )

            else:                  # cardinal arrow
                btn.setFont(arrow_font)
                btn.setStyleSheet(
                    "background:#21262d; color:#e6edf3; border:1px solid #484f58;"
                    "border-radius:3px; min-height:0;"
                )
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _dx, _dy = dx, dy
                btn.clicked.connect(
                    lambda _, x=_dx, y=_dy: self._do_jog(
                        x * self._step.value(), y * self._step.value()
                    )
                )

            grid.addWidget(btn, r, c)

        # Center the jog grid
        jog_row = QHBoxLayout(); jog_row.setContentsMargins(0,0,0,0)
        jog_row.addStretch(); jog_row.addWidget(jog_wrap); jog_row.addStretch()
        lay.addSpacing(18)
        lay.addLayout(jog_row)
        lay.addSpacing(10)

        # ── Move To — button + X/Y on two lines ──────────────────────
        mvb = self._B("Move To", 22); mvb.clicked.connect(self._do_move)
        lay.addWidget(mvb)

        xy_row = QHBoxLayout(); xy_row.setSpacing(4); xy_row.setContentsMargins(0,0,0,0)
        xy_row.addWidget(self._lbl("X"))
        self._mx = self._spin(-400, 400, 0, 22, w=70)
        xy_row.addWidget(self._mx)
        xy_row.addWidget(self._lbl("Y"))
        self._my = self._spin(-400, 400, 0, 22, w=70)
        xy_row.addWidget(self._my)
        lay.addLayout(xy_row)

        lay.addSpacing(8)
        lay.addWidget(_divider())
        lay.addSpacing(8)

        # ── Mode buttons + speed (like K40 Whisperer) ────────────────
        # Each row: [Clickable Mode Button] [speed spinbox]
        # Clicking the mode button starts that operation immediately.

        def mode_row(label, color, default, on_click):
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"background:{color}; color:#fff; border:none;"
                f"border-radius:4px; font-size:11px; font-weight:bold;"
                f"text-align:left; padding-left:8px;"
                f"min-height:0; max-height:26px;"
            )
            btn.clicked.connect(on_click)
            sp = QDoubleSpinBox()
            sp.setRange(1, 500); sp.setValue(default)
            sp.setDecimals(0)
            sp.setFixedHeight(26)
            sp.setFixedWidth(82)
            sp.setSuffix(" mm/s")
            sp.setStyleSheet("font-size:10px; font-weight:bold;")
            r = QHBoxLayout(); r.setSpacing(4); r.setContentsMargins(0,0,0,0)
            r.addWidget(btn, 1); r.addWidget(sp)
            lay.addLayout(r)
            return sp

        self._spd_raster = mode_row(
            "▶  Raster Engrave", "#1a3a5c", 200,
            lambda: self._do_mode("raster"))
        self._spd_vector = mode_row(
            "▶  Vector Engrave", "#1a3a5c", 20,
            lambda: self._do_mode("engrave"))
        self._spd_cut    = mode_row(
            "▶  Vector Cut",     "#238636", 8,
            lambda: self._do_mode("cut"))

        # Passes
        p_row = QHBoxLayout(); p_row.setSpacing(4); p_row.setContentsMargins(0,0,0,0)
        p_row.addWidget(self._lbl("Passes:"))
        self._passes = QSpinBox()
        self._passes.setRange(1, 10); self._passes.setFixedHeight(22)
        self._passes.setFixedWidth(55); self._passes.setStyleSheet("font-size:11px;")
        p_row.addWidget(self._passes); p_row.addStretch()
        lay.addLayout(p_row)

        lay.addSpacing(8)
        lay.addWidget(_divider())
        lay.addSpacing(8)

        # ── Trace + STOP ──────────────────────────────────────────────
        tr = self._B("Trace Outline", 24, "#1a2e4a")
        tr.setStyleSheet(
            "background:#1a2e4a; color:#58a6ff; border:1px solid #1f6feb;"
            "border-radius:3px; font-size:11px; min-height:0; max-height:24px;"
        )
        tr.clicked.connect(self._do_trace)
        lay.addWidget(tr)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100); self._progress.setValue(0)
        self._progress.setFixedHeight(4); self._progress.setVisible(False)
        lay.addWidget(self._progress)

        self._job_lbl = QLabel()
        self._job_lbl.setStyleSheet("color:#d29922; font-size:10px; border:none;")
        self._job_lbl.setVisible(False)
        lay.addWidget(self._job_lbl)

        stop = QPushButton("Stop")
        stop.setFixedHeight(32)
        stop.setStyleSheet(
            "background:#b62324; color:#fff; border:none; border-radius:4px;"
            "font-size:13px; font-weight:bold; min-height:0; max-height:32px;"
        )
        stop.clicked.connect(self._do_stop)
        lay.addWidget(stop)

        lay.addStretch()
        scroll.setWidget(inner)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(scroll)

    # ------------------------------------------------------------------ machine select

    def set_machine(self, machine_id: int):
        self._machine_id = machine_id
        with get_session() as s:
            m = s.get(Machine, machine_id)
            if m:
                self._name_lbl.setText(m.name)
                self._mx.setMaximum(m.bed_width_mm or 400)
                self._my.setMaximum(m.bed_height_mm or 400)
                # Load this machine's saved speeds
                self._spd_raster.setValue(m.raster_speed or 200)
                self._spd_vector.setValue(m.vector_engrave_speed or 20)
                self._spd_cut.setValue(m.vector_cut_speed or 8)
                self._passes.setValue(m.vector_cut_passes or 1)
        self._refresh_conn()

    def _open_settings(self):
        if self._machine_id is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Machine", "Select a machine first.")
            return
        from app.ui.dialogs.machine_settings_dialog import MachineSettingsDialog
        dlg = MachineSettingsDialog(self._machine_id, self)
        if dlg.exec():
            # Reload speeds after settings saved
            self.set_machine(self._machine_id)

    def _refresh_conn(self):
        if self._machine_id is None:
            return
        drv = machine_manager.status(self._machine_id)
        if drv.connected:
            self._status_dot.setStyleSheet("color:#3fb950; font-size:14px;")
            self._conn_btn.setText("Disconnect")
            self._conn_btn.setStyleSheet(
                "background:#3a0000; color:#f85149; border:1px solid #b62324;"
                "border-radius:6px; font-weight:bold;"
            )
            self._progress.setVisible(drv.busy)
            if drv.busy:
                self._progress.setValue(int(drv.progress))
        else:
            self._status_dot.setStyleSheet("color:#6e7681; font-size:14px;")
            self._conn_btn.setText("Connect")
            self._conn_btn.setObjectName("AccentButton")
            self._conn_btn.setStyleSheet("")
            self._conn_btn.style().unpolish(self._conn_btn)
            self._conn_btn.style().polish(self._conn_btn)

    # ------------------------------------------------------------------ commands

    def _toggle_connect(self):
        if self._machine_id is None:
            return
        drv = machine_manager.status(self._machine_id)
        if drv.connected:
            machine_manager.disconnect(self._machine_id)
            with get_session() as s:
                m = s.get(Machine, self._machine_id)
                if m: m.status = MachineStatus.offline; s.commit()
        else:
            with get_session() as s:
                m = s.get(Machine, self._machine_id)
                vid = int(m.usb_vendor_id,  16) if m else 0x1a86
                pid = int(m.usb_product_id, 16) if m else 0x5512
                sn  = m.serial_number       if m else ""
            ok = machine_manager.connect(self._machine_id, vendor_id=vid,
                                         product_id=pid, serial=sn)
            with get_session() as s:
                m = s.get(Machine, self._machine_id)
                if m:
                    m.status = MachineStatus.idle if ok else MachineStatus.error
                    s.commit()
            if not ok:
                QMessageBox.warning(
                    self, "Connection Failed",
                    machine_manager.status(self._machine_id).message
                )
        self._refresh_conn()

    def _cmd(self, fn):
        if self._machine_id: fn(self._machine_id)

    def _initialize(self):
        if self._check(): cmd_initialize(self._machine_id)

    def _do_jog(self, dx, dy):
        if self._check():
            cmd_jog(self._machine_id, dx, dy)
            drv = machine_manager._drivers.get(self._machine_id)
            if drv:
                drv._pos_x = getattr(drv, "_pos_x", 0.0) + dx
                drv._pos_y = getattr(drv, "_pos_y", 0.0) + dy

    def _do_move(self):
        if self._check():
            cmd_move_to(self._machine_id, self._mx.value(), self._my.value())

    def _do_stop(self):
        if self._machine_id: cmd_stop(self._machine_id)
        if self._active_job:  self._active_job.abort()

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Design File", str(Path.home()),
            "Design Files (*.svg *.dxf)"
        )
        if path: self.load_file(path)

    def _reload_file(self):
        if self._file_path: self.load_file(self._file_path)

    def load_file(self, path: str):
        self._file_path = path
        self._file_lbl.setText(Path(path).name)
        # Signal parent to update canvas
        p = self.parent()
        while p and not isinstance(p, MachinesPage):
            p = p.parent()
        if p:
            p.load_file_to_canvas(path)

    def _do_mode(self, mode: str):
        """Raster Engrave / Vector Engrave / Vector Cut buttons."""
        if not self._check(): return
        if not self._file_path:
            QMessageBox.information(self, "No File", "Open a design file first.")
            return
        mode_names = {"raster": "Raster Engrave", "engrave": "Vector Engrave", "cut": "Vector Cut"}
        spd = {"raster": self._spd_raster, "engrave": self._spd_vector, "cut": self._spd_cut}[mode]
        reply = QMessageBox.question(
            self, mode_names[mode],
            f"Mode:   {mode_names[mode]}\n"
            f"File:   {Path(self._file_path).name}\n"
            f"Speed:  {spd.value():.0f} mm/s    Passes: {self._passes.value()}\n\n"
            "Material loaded and cover closed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            from app.services.telegram_service import telegram_service
            telegram_service.notify_job_started(
                mode_names[mode], Path(self._file_path).name, 1, self._name_lbl.text()
            )
            self._run_job(trace_only=False, mode=mode)

    def _do_trace(self):
        if not self._check(): return
        if not self._file_path:
            QMessageBox.information(self, "No File", "Open a design file first."); return
        self._run_job(trace_only=True)

    def _do_cut(self):
        # Legacy — calls Vector Cut mode
        self._do_mode("cut")

    def _run_job(self, trace_only: bool, mode: str = "cut"):
        # Pick active speed based on mode
        spd_map = {
            "cut":     self._spd_cut.value(),
            "engrave": self._spd_vector.value(),
            "raster":  self._spd_raster.value(),
        }
        active_spd = spd_map.get(mode, self._spd_cut.value())
        settings = CutSettings(
            speed_cut_mm_s=active_spd,
            speed_vector_mm_s=active_spd,
            speed_raster_mm_s=active_spd,
            passes=self._passes.value(),
        )
        self._progress.setVisible(True); self._progress.setValue(0)
        self._job_lbl.setVisible(True)
        self._job_lbl.setText("Tracing…" if trace_only else "Cutting…")

        def _prog(pct, msg):
            self._progress.setValue(int(pct))
            self._job_lbl.setText(msg[:28])

        def _done(ok, msg):
            self._progress.setVisible(False)
            self._job_lbl.setVisible(False)
            if not trace_only:
                from app.services.telegram_service import telegram_service
                _mode_labels = {"cut": "Vector Cut", "engrave": "Vector Engrave", "raster": "Raster Engrave"}
                label = _mode_labels.get(mode, mode)
                if ok:
                    telegram_service.notify_job_completed(
                        label, Path(self._file_path).name, 1, self._name_lbl.text()
                    )
                else:
                    telegram_service.notify_job_failed(
                        label, Path(self._file_path).name, msg
                    )
            if not ok and not trace_only:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Job Error", msg))

        job = LaserJob(
            machine_id=self._machine_id, file_path=self._file_path,
            settings=settings, trace_only=trace_only,
            on_progress=_prog, on_done=_done,
        )
        self._active_job = job; job.start()

    def _check(self) -> bool:
        if self._machine_id is None:
            QMessageBox.information(self, "No Machine", "Select a machine first."); return False
        if not machine_manager.status(self._machine_id).connected:
            QMessageBox.warning(self, "Not Connected",
                "Connect the machine first."); return False
        return True


# ─────────────────────────────────────────────────────────────────────
# Panel 4 — Pending Jobs Queue
# ─────────────────────────────────────────────────────────────────────

class ConfirmCutDialog(QDialog):
    """'Cutting [product] on [machine]? How many sets?' → marks directly as done."""

    def __init__(self, item_id: int, machine_id: Optional[int], parent=None):
        super().__init__(parent)
        self._item_id    = item_id
        self._machine_id = machine_id
        self.setWindowTitle("Confirm Cut")
        self.setFixedSize(360, 200)
        self.setModal(True)
        self._build()

    def _build(self):
        with get_session() as s:
            item = s.get(JobItem, self._item_id)
            prod_name    = item.product.name if item and item.product else "?"
            self._pending = item.quantity_pending if item else 1
            mach_name = ""
            if self._machine_id:
                from app.core.database import Machine
                m = s.get(Machine, self._machine_id)
                mach_name = m.name if m else ""

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 18, 20, 16)

        prod_lbl = QLabel(prod_name)
        prod_lbl.setStyleSheet(
            "font-size:14px; font-weight:bold; color:#e6edf3;"
        )
        lay.addWidget(prod_lbl)

        if mach_name:
            mach_lbl = QLabel(f"Machine: {mach_name}")
            mach_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
            lay.addWidget(mach_lbl)

        pend_lbl = QLabel(f"Pending: {self._pending} set{'s' if self._pending!=1 else ''}")
        pend_lbl.setStyleSheet("color:#d29922; font-size:11px;")
        lay.addWidget(pend_lbl)

        qty_row = QHBoxLayout(); qty_row.setSpacing(8)
        qty_row.addWidget(QLabel("Sets done:").also(
            lambda l: l.setStyleSheet("color:#8b949e; font-size:11px;")
        ))
        from PyQt6.QtWidgets import QSpinBox
        self._qty = QSpinBox()
        self._qty.setRange(1, max(1, self._pending))
        self._qty.setValue(1)
        self._qty.setFixedWidth(70)
        qty_row.addWidget(self._qty)
        qty_row.addStretch()
        lay.addLayout(qty_row)

        lay.addStretch()

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        ok_btn = QPushButton("✓  Mark Done")
        ok_btn.setFixedHeight(32)
        ok_btn.setStyleSheet(
            "background:#238636; color:#fff; border:none; border-radius:4px;"
            "font-size:12px; font-weight:bold; min-height:0; max-height:32px;"
        )
        ok_btn.clicked.connect(self._confirm)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

    def _confirm(self):
        qty = self._qty.value()
        from datetime import datetime as _dt
        from app.core.database import JobRun, RunStatus, JobSheetStatus
        from app.services.telegram_service import telegram_service
        with get_session() as s:
            item  = s.get(JobItem, self._item_id)
            if not item:
                self.reject(); return
            sheet = item.job_sheet
            prod_name  = item.product.name if item.product else "?"
            sheet_name = sheet.name if sheet else "?"

            # Mark as completed directly (no in-progress state)
            item.quantity_completed  += qty
            item.quantity_in_progress = max(0, item.quantity_in_progress)

            # Check if sheet fully done
            sheet_done = sheet and all(i.is_done for i in sheet.items)
            if sheet_done and sheet:
                sheet.status = JobSheetStatus.completed
            elif sheet and sheet.status == JobSheetStatus.open:
                sheet.status = JobSheetStatus.in_progress

            mach_name = ""
            if self._machine_id:
                from app.core.database import Machine
                m = s.get(Machine, self._machine_id)
                mach_name = m.name if m else "?"

            s.commit()

        telegram_service.notify_job_completed(sheet_name, prod_name, qty, mach_name)
        if sheet_done:
            telegram_service.notify_job_sheet_done(sheet_name)

        self.accept()


class JobQueuePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._machine_id: Optional[int] = None
        self.setFixedWidth(336)
        self.setStyleSheet("background:#0d1117; border-left:1px solid #21262d;")
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QTabWidget
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet("background:#010409; border-bottom:1px solid #21262d;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10, 6, 6, 6); hl.setSpacing(4)
        lbl = QLabel("TASK QUEUE")
        lbl.setStyleSheet(
            "color:#6e7681; font-size:10px; font-weight:bold;"
            "letter-spacing:1px; background:transparent; border:none;"
        )
        hl.addWidget(lbl, 1)
        new_btn = QPushButton("+ New Job")
        new_btn.setFixedHeight(20)
        new_btn.setStyleSheet(
            "background:#238636; color:#fff; border:none; border-radius:3px;"
            "font-size:10px; font-weight:bold; padding:0 6px; min-height:0; max-height:20px;"
        )
        new_btn.clicked.connect(self._create_job)
        hl.addWidget(new_btn)
        ref = QPushButton("↺"); ref.setFixedSize(20, 20)
        ref.setStyleSheet(
            "background:#21262d; color:#6e7681; border:1px solid #30363d;"
            "border-radius:3px; font-size:10px; min-height:0; max-height:20px;"
        )
        ref.clicked.connect(self.refresh)
        hl.addWidget(ref)
        lay.addWidget(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane{border:none;}"
            "QTabBar::tab{background:#010409; color:#6e7681; border:none;"
            "padding:5px 10px; font-size:10px;}"
            "QTabBar::tab:selected{color:#e6edf3; border-bottom:2px solid #58a6ff;}"
        )

        self._pending_widget = QWidget()
        self._pending_widget.setStyleSheet("background:#0d1117;")
        self._pending_lay = QVBoxLayout(self._pending_widget)
        self._pending_lay.setContentsMargins(10, 10, 10, 10)
        self._pending_lay.setSpacing(8)
        ps = QScrollArea(); ps.setWidgetResizable(True)
        ps.setFrameShape(QFrame.Shape.NoFrame)
        ps.setWidget(self._pending_widget)
        self._tabs.addTab(ps, "Pending")

        lay.addWidget(self._tabs, 1)

    def _create_job(self):
        from app.ui.dialogs.create_job_dialog import CreateJobDialog
        dlg = CreateJobDialog(self)
        if dlg.exec():
            self.refresh()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def refresh(self):
        self._clear_layout(self._pending_lay)
        self._build_pending()

    def _build_pending(self):
        with get_session() as s:
            sheets = (
                s.query(JobSheet)
                .filter(JobSheet.status.in_([JobSheetStatus.open, JobSheetStatus.in_progress]))
                .order_by(JobSheet.updated_at.desc()).all()
            )
            rows = []
            for sh in sheets:
                for item in sh.items:
                    if item.quantity_pending > 0:
                        rows.append((
                            item.id,
                            item.product.name if item.product else "?",
                            item.quantity_pending,
                            sh.name,
                        ))

        if not rows:
            lbl = QLabel("No pending items")
            lbl.setStyleSheet("color:#6e7681; font-size:11px; padding:12px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._pending_lay.addWidget(lbl)
            self._pending_lay.addStretch()
            self._tabs.setTabText(0, "Pending")
            return

        self._tabs.setTabText(0, f"Pending ({len(rows)})")

        for item_id, prod_name, qty, sheet_name in rows:
            card = QFrame()
            card.setStyleSheet(
                "background:#161b22; border:1px solid #30363d; border-radius:4px;"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(6)

            name_btn = QPushButton(prod_name)
            name_btn.setStyleSheet(
                "color:#58a6ff; font-size:13px; font-weight:bold; border:none;"
                "background:transparent; text-align:left; padding:0; text-decoration:underline;"
            )
            name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            name_btn.setToolTip("Click to open this product's folder and load a file")
            iid = item_id
            name_btn.clicked.connect(lambda _, i=iid: self._open_product_folder(i))
            cl.addWidget(name_btn)

            info_row = QHBoxLayout(); info_row.setSpacing(8)
            qty_lbl = QLabel(f"{qty} set{'s' if qty!=1 else ''} pending")
            qty_lbl.setStyleSheet("color:#d29922; font-size:12px; border:none;")
            info_row.addWidget(qty_lbl, 1)

            cut_btn = QPushButton("✓  Cut")
            cut_btn.setFixedHeight(28)
            cut_btn.setMinimumWidth(72)
            cut_btn.setStyleSheet(
                "background:#238636; color:#fff; border:none; border-radius:4px;"
                "font-size:12px; font-weight:bold; min-height:0; max-height:28px;"
            )
            iid = item_id
            cut_btn.clicked.connect(lambda _, i=iid: self._confirm_cut(i))
            info_row.addWidget(cut_btn)
            cl.addLayout(info_row)

            job_lbl = QLabel(sheet_name)
            job_lbl.setStyleSheet("color:#484f58; font-size:11px; border:none;")
            cl.addWidget(job_lbl)

            self._pending_lay.addWidget(card)

        self._pending_lay.addStretch()

    def _open_product_folder(self, item_id: int):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from app.core.database import JobItem

        with get_session() as s:
            item = s.get(JobItem, item_id)
            if not item or not item.product:
                return
            folder = item.product.folder_path or ""
            prod_name = item.product.name

        if not folder or not Path(folder).exists():
            QMessageBox.information(
                self, "No Folder Set",
                f"No folder is set for '{prod_name}'.\n\n"
                "Go to Library → Edit Product → Browse to set the folder."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, f"Select file for  {prod_name}",
            folder,
            "Design Files (*.svg *.dxf)"
        )
        if not path:
            return

        # Walk up to MachinesPage and load the file into the canvas
        p = self.parent()
        while p and not isinstance(p, MachinesPage):
            p = p.parent()
        if p:
            p.load_file_to_canvas(path)

    def _confirm_cut(self, item_id: int):
        dlg = ConfirmCutDialog(item_id, self._machine_id, self)
        if dlg.exec():
            self.refresh()


# ─────────────────────────────────────────────────────────────────────
# Main Machines Page — 4-panel layout
# ─────────────────────────────────────────────────────────────────────

class MachinesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_id: Optional[int] = None
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(2000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame(); header.setObjectName("HeaderBar")
        h = QHBoxLayout(header); h.setContentsMargins(24, 16, 24, 12)
        tc = QVBoxLayout()
        t = QLabel("Machines"); t.setObjectName("PageTitle"); tc.addWidget(t)
        self._sub = QLabel("Select a machine to control")
        self._sub.setObjectName("PageSubtitle"); tc.addWidget(self._sub)
        h.addLayout(tc); h.addStretch()
        root.addWidget(header)

        # 4-panel splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle{background:#21262d;}")

        # Panel 1: Machine list
        self._machine_list = MachineListPanel(self._on_machine_select)
        splitter.addWidget(self._machine_list)

        # Panel 2: Control panel
        self._control = ControlPanel()
        splitter.addWidget(self._control)

        # Panel 3: Bed canvas + status
        canvas_widget = QWidget()
        canvas_widget.setStyleSheet("background:#0d1117;")
        cv = QVBoxLayout(canvas_widget)
        cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(0)

        self._canvas = BedPreview(400, 400)
        cv.addWidget(self._canvas, 1)

        # Canvas status bar
        status_bar = QWidget()
        status_bar.setStyleSheet(
            "background:#010409; border-top:1px solid #21262d;"
        )
        sb = QHBoxLayout(status_bar)
        sb.setContentsMargins(16, 5, 16, 5); sb.setSpacing(20)
        # Status bar matches K40 Whisperer format
        self._pos_lbl = QLabel("Current Position:  X = 0.000   Y = 0.000")
        self._pos_lbl.setStyleSheet(
            "color:#8b949e; font-size:11px; font-family:Consolas,monospace;"
        )
        sb.addWidget(self._pos_lbl)
        self._file_status = QLabel("( W × H ) = ( — )")
        self._file_status.setStyleSheet(
            "color:#6e7681; font-size:11px; font-family:Consolas,monospace;"
        )
        sb.addWidget(self._file_status)
        sb.addStretch()
        self._mach_status = QLabel("No machine selected")
        self._mach_status.setStyleSheet("color:#6e7681; font-size:11px;")
        sb.addWidget(self._mach_status)
        cv.addWidget(status_bar)

        splitter.addWidget(canvas_widget)

        # Panel 4: Job queue
        self._queue = JobQueuePanel()
        splitter.addWidget(self._queue)

        splitter.setSizes([160, 265, 600, 230])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(3, False)

        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------ machine select

    def _on_machine_select(self, machine_id: int):
        self._selected_id = machine_id
        self._queue._machine_id = machine_id   # pass machine to queue panel
        self._control.set_machine(machine_id)
        with get_session() as s:
            m = s.get(Machine, machine_id)
            if m:
                self._canvas.bed_w = m.bed_width_mm
                self._canvas.bed_h = m.bed_height_mm
                self._sub.setText(f"Controlling:  {m.name}")
                self._canvas.update()

    # ------------------------------------------------------------------ canvas

    def load_file_to_canvas(self, file_path: str):
        self._canvas.load_file(file_path)
        self._control._file_path = file_path
        self._control._file_lbl.setText(Path(file_path).name)
        # Compute bounding box for status bar (like K40W)
        try:
            from app.core.svg_to_path import file_to_polylines
            polys = file_to_polylines(file_path)
            if polys:
                all_pts = [pt for p in polys for pt in p]
                w = max(p[0] for p in all_pts) - min(p[0] for p in all_pts)
                h = max(p[1] for p in all_pts) - min(p[1] for p in all_pts)
                self._file_status.setText(
                    f"( W × H ) = ( {w:.3f} mm × {h:.3f} mm )"
                )
            else:
                self._file_status.setText(f"File: {Path(file_path).name}")
        except Exception:
            self._file_status.setText(f"File: {Path(file_path).name}")

    # ------------------------------------------------------------------ refresh tick

    def _tick(self):
        self._machine_list.refresh(self._selected_id)
        self._control._refresh_conn()

        # Update head position on canvas
        if self._selected_id is not None:
            drv = machine_manager._drivers.get(self._selected_id)
            if drv:
                x = getattr(drv, "_pos_x", 0.0)
                y = getattr(drv, "_pos_y", 0.0)
                self._pos_lbl.setText(f"X = {x:7.2f} mm   Y = {y:7.2f} mm")
                self._canvas.set_head_position(x, y)

            status = machine_manager.status(self._selected_id)
            badge = "BUSY" if status.busy else "IDLE" if status.connected else "OFFLINE"
            color = "#d29922" if status.busy else "#3fb950" if status.connected else "#6e7681"
            self._mach_status.setText(badge)
            self._mach_status.setStyleSheet(f"color:{color}; font-size:11px; font-weight:bold;")

    def refresh(self):
        self._machine_list.refresh(self._selected_id)
        self._queue.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._machine_list.refresh(self._selected_id)
        self._queue.refresh()
