"""
Per-machine settings dialog — mirrors K40 Whisperer's
General / Raster / Rotary / Advanced settings, saved per machine.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QComboBox,
    QDoubleSpinBox, QSpinBox, QPushButton,
    QTabWidget, QWidget, QFrame, QSlider,
    QDialogButtonBox, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt

from app.core.database import get_session, Machine


def _title(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        "color:#8b949e; font-size:10px; font-weight:bold;"
        "letter-spacing:1px; border:none; background:transparent;"
        "padding:8px 0 4px 0;"
    )
    return l


def _divider() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background:#21262d; max-height:1px; margin:4px 0;")
    return f


class MachineSettingsDialog(QDialog):
    """
    Settings dialog for a single machine.
    Tabs: General | Raster | Rotary | Advanced
    """

    def __init__(self, machine_id: int, parent=None):
        super().__init__(parent)
        self._machine_id = machine_id
        self.setWindowTitle("Machine Settings")
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)
        self.setModal(True)
        self._load_machine()
        self._build()
        self._populate()

    # ------------------------------------------------------------------ load

    def _load_machine(self):
        with get_session() as s:
            self._m = s.get(Machine, self._machine_id)

    # ------------------------------------------------------------------ build

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(16, 14, 16, 14)

        # Machine name header
        name = getattr(self._m, "name", "Machine")
        hdr = QLabel(f"Settings for:  {name}")
        hdr.setStyleSheet(
            "font-size:15px; font-weight:bold; color:#e6edf3; border:none;"
        )
        root.addWidget(hdr)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_general(),  "General")
        tabs.addTab(self._build_raster(),   "Raster")
        tabs.addTab(self._build_rotary(),   "Rotary")
        tabs.addTab(self._build_advanced(), "Advanced")
        root.addWidget(tabs, 1)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        ok = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Save Settings")
        ok.setObjectName("PrimaryButton")
        ok.style().unpolish(ok); ok.style().polish(ok)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ------------------------------------------------------------------ General tab

    def _build_general(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setSpacing(6); lay.setContentsMargins(12, 10, 12, 10)

        form = QFormLayout(); form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._units = QComboBox()
        self._units.addItems(["mm", "inch"])
        form.addRow("Units", self._units)

        self._board = QComboBox()
        self._board.addItems(["LASER-M2", "LASER-M3"])
        self._board.currentTextChanged.connect(self._on_board_changed)
        form.addRow("Board Type", self._board)

        self._bed_w = QDoubleSpinBox()
        self._bed_w.setRange(10, 2000); self._bed_w.setSuffix(" mm")
        form.addRow("Laser Area Width",  self._bed_w)

        self._bed_h = QDoubleSpinBox()
        self._bed_h.setRange(10, 2000); self._bed_h.setSuffix(" mm")
        form.addRow("Laser Area Height", self._bed_h)

        self._x_scale = QDoubleSpinBox()
        self._x_scale.setRange(0.01, 10); self._x_scale.setDecimals(3)
        self._x_scale.setSingleStep(0.001)
        form.addRow("X Scale Factor", self._x_scale)

        self._y_scale = QDoubleSpinBox()
        self._y_scale.setRange(0.01, 10); self._y_scale.setDecimals(3)
        self._y_scale.setSingleStep(0.001)
        form.addRow("Y Scale Factor", self._y_scale)

        lay.addLayout(form)
        lay.addWidget(_divider())

        # Checkboxes
        self._home_on_init   = QCheckBox("Home Upon Initialize")
        self._home_upper_right = QCheckBox("Home in Upper Right")
        self._wait_laser     = QCheckBox("Wait for Laser to Finish")
        self._unlock_after   = QCheckBox("Unlock Rail After Job")
        self._preprocess_crc = QCheckBox("Preprocess CRC Data")
        self._reduce_mem     = QCheckBox("Reduce Memory Use")

        for cb in [self._home_on_init, self._home_upper_right,
                   self._wait_laser, self._unlock_after,
                   self._preprocess_crc, self._reduce_mem]:
            lay.addWidget(cb)

        lay.addWidget(_divider())

        # M3 section
        self._m3_group = QGroupBox("Laser-M3 Options")
        m3lay = QFormLayout(self._m3_group)
        m3lay.setSpacing(6)
        self._max_power = QSpinBox()
        self._max_power.setRange(1, 100); self._max_power.setSuffix(" %")
        m3lay.addRow("Maximum Power Setting", self._max_power)
        warn = QLabel("Setting this too high may damage laser tube")
        warn.setStyleSheet("color:#d29922; font-size:10px; border:none;")
        m3lay.addRow("", warn)
        lay.addWidget(self._m3_group)

        lay.addStretch()
        return w

    def _on_board_changed(self, txt: str):
        self._m3_group.setEnabled(txt == "LASER-M3")

    # ------------------------------------------------------------------ Raster tab

    def _build_raster(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setSpacing(8); lay.setContentsMargins(12, 10, 12, 10)

        form = QFormLayout(); form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._scanline = QDoubleSpinBox()
        self._scanline.setRange(0.0001, 1.0); self._scanline.setDecimals(4)
        self._scanline.setSingleStep(0.001); self._scanline.setSuffix(" in")
        form.addRow("Scanline Step", self._scanline)

        self._halftone_res = QComboBox()
        self._halftone_res.addItems(["250", "333", "500", "1000"])
        self._halftone_res.setEditable(True)
        form.addRow("Halftone Resolution", self._halftone_res)

        lay.addLayout(form)

        self._engrave_bottom_up = QCheckBox("Engrave Bottom Up")
        self._halftone_dither   = QCheckBox("Halftone (Dither)")
        lay.addWidget(self._engrave_bottom_up)
        lay.addWidget(self._halftone_dither)

        lay.addWidget(_divider())

        # Sliders — match K40W's black/white/transition sliders
        def _slider_row(label: str, lo: float, hi: float, steps: int):
            sl_row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#8b949e; font-size:11px; border:none;")
            lbl.setFixedWidth(140)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, steps)
            sl.setSingleStep(1)
            val = QLabel()
            val.setFixedWidth(40)
            val.setStyleSheet("color:#e6edf3; font-size:11px; border:none;")
            def _upd(v, sl=sl, lo=lo, hi=hi, steps=steps, val=val):
                fv = lo + (hi - lo) * v / steps
                val.setText(f"{fv:.2f}")
            sl.valueChanged.connect(_upd)
            sl_row.addWidget(lbl); sl_row.addWidget(sl, 1); sl_row.addWidget(val)
            lay.addLayout(sl_row)
            return sl, lo, hi, steps

        self._slope_black_sl, *self._sb_meta = _slider_row("Slope, Black", 0.0, 10.0, 100)
        self._slope_white_sl, *self._sw_meta = _slider_row("Slope, White", 0.0, 2.0, 100)
        self._transition_sl,  *self._tr_meta = _slider_row("Transition",   0.0, 10.0, 100)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ Rotary tab

    def _build_rotary(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setSpacing(8); lay.setContentsMargins(12, 10, 12, 10)

        self._use_rotary = QCheckBox("Use Rotary Settings")
        self._use_rotary.toggled.connect(self._on_rotary_toggle)
        lay.addWidget(self._use_rotary)
        lay.addWidget(_divider())

        self._rotary_group = QWidget()
        rg_lay = QFormLayout(self._rotary_group)
        rg_lay.setSpacing(8)
        rg_lay.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._rotary_scale = QDoubleSpinBox()
        self._rotary_scale.setRange(0.001, 100); self._rotary_scale.setDecimals(3)
        rg_lay.addRow("Rotary Scale Factor (Y axis)", self._rotary_scale)

        self._rotary_rapid = QDoubleSpinBox()
        self._rotary_rapid.setRange(0, 500); self._rotary_rapid.setSuffix(" mm/s")
        rg_lay.addRow("Rapid Speed (default=0)", self._rotary_rapid)

        lay.addWidget(self._rotary_group)
        lay.addStretch()
        self._on_rotary_toggle(False)
        return w

    def _on_rotary_toggle(self, on: bool):
        self._rotary_group.setEnabled(on)

    # ------------------------------------------------------------------ Advanced tab

    def _build_advanced(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setSpacing(6); lay.setContentsMargins(12, 10, 12, 10)

        self._raster_color    = QCheckBox("Raster Color")
        self._mirror_design   = QCheckBox("Mirror Design")
        self._rotate_design   = QCheckBox("Rotate Design")
        self._use_input_csys  = QCheckBox("Use Input CSYS")
        self._cut_inside_first= QCheckBox("Cut Inside First")
        self._group_engrave   = QCheckBox("Group Engrave Tasks")
        self._group_vector    = QCheckBox("Group Vector Tasks")

        for cb in [self._raster_color, self._mirror_design, self._rotate_design,
                   self._use_input_csys, self._cut_inside_first,
                   self._group_engrave, self._group_vector]:
            lay.addWidget(cb)

        lay.addWidget(_divider())

        # Pass counts
        form = QFormLayout(); form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._r_passes  = QSpinBox(); self._r_passes.setRange(1, 20)
        self._ve_passes = QSpinBox(); self._ve_passes.setRange(1, 20)
        self._vc_passes = QSpinBox(); self._vc_passes.setRange(1, 20)
        form.addRow("Raster Eng. Passes",  self._r_passes)
        form.addRow("Vector Eng. Passes",  self._ve_passes)
        form.addRow("Vector Cut Passes",   self._vc_passes)
        lay.addLayout(form)

        lay.addWidget(_divider())

        # Speed & Power per machine
        lay.addWidget(_title("SPEED & POWER"))
        sp_form = QFormLayout(); sp_form.setSpacing(6)
        sp_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _sp(default, suffix):
            s = QDoubleSpinBox(); s.setRange(1, 500)
            s.setValue(default); s.setSuffix(suffix)
            s.setDecimals(0); return s

        self._raster_spd  = _sp(200, " mm/s")
        self._ve_spd      = _sp(20,  " mm/s")
        self._vc_spd      = _sp(8,   " mm/s")
        self._raster_pwr  = QSpinBox(); self._raster_pwr.setRange(1,100); self._raster_pwr.setSuffix(" %")
        self._ve_pwr      = QSpinBox(); self._ve_pwr.setRange(1,100); self._ve_pwr.setSuffix(" %")
        self._vc_pwr      = QSpinBox(); self._vc_pwr.setRange(1,100); self._vc_pwr.setSuffix(" %")

        sp_form.addRow("Raster Engrave Speed",  self._raster_spd)
        sp_form.addRow("Raster Engrave Power",  self._raster_pwr)
        sp_form.addRow("Vector Engrave Speed",  self._ve_spd)
        sp_form.addRow("Vector Engrave Power",  self._ve_pwr)
        sp_form.addRow("Vector Cut Speed",      self._vc_spd)
        sp_form.addRow("Vector Cut Power",      self._vc_pwr)
        lay.addLayout(sp_form)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------ populate

    def _populate(self):
        m = self._m
        if not m: return

        # General
        self._units.setCurrentText(m.units or "mm")
        self._board.setCurrentText(m.board_type or "LASER-M2")
        self._bed_w.setValue(m.bed_width_mm or 400)
        self._bed_h.setValue(m.bed_height_mm or 400)
        self._x_scale.setValue(m.x_scale_factor or 1.0)
        self._y_scale.setValue(m.y_scale_factor or 1.0)
        self._home_on_init.setChecked(bool(m.home_upon_initialize))
        self._home_upper_right.setChecked(bool(m.home_in_upper_right))
        self._wait_laser.setChecked(bool(m.wait_for_laser))
        self._unlock_after.setChecked(bool(m.unlock_rail_after_job))
        self._preprocess_crc.setChecked(bool(m.preprocess_crc))
        self._reduce_mem.setChecked(bool(m.reduce_memory))
        self._max_power.setValue(m.max_power_pct or 30)
        self._m3_group.setEnabled((m.board_type or "") == "LASER-M3")

        # Raster
        self._scanline.setValue(m.scanline_step or 0.002)
        idx = self._halftone_res.findText(str(m.halftone_resolution or 500))
        if idx >= 0: self._halftone_res.setCurrentIndex(idx)
        else: self._halftone_res.setCurrentText(str(m.halftone_resolution or 500))
        self._engrave_bottom_up.setChecked(bool(m.engrave_bottom_up))
        self._halftone_dither.setChecked(bool(m.halftone_dither))
        self._slope_black_sl.setValue(int((m.slope_black or 2.5) / 10.0 * 100))
        self._slope_white_sl.setValue(int((m.slope_white or 0.5) / 2.0 * 100))
        self._transition_sl.setValue(int((m.transition or 3.5) / 10.0 * 100))

        # Rotary
        self._use_rotary.setChecked(bool(m.use_rotary))
        self._rotary_scale.setValue(m.rotary_scale_y or 1.0)
        self._rotary_rapid.setValue(m.rotary_rapid_speed or 0.0)
        self._on_rotary_toggle(bool(m.use_rotary))

        # Advanced
        self._raster_color.setChecked(bool(m.raster_color))
        self._mirror_design.setChecked(bool(m.mirror_design))
        self._rotate_design.setChecked(bool(m.rotate_design))
        self._use_input_csys.setChecked(bool(m.use_input_csys))
        self._cut_inside_first.setChecked(bool(m.cut_inside_first))
        self._group_engrave.setChecked(bool(m.group_engrave_tasks))
        self._group_vector.setChecked(bool(m.group_vector_tasks))
        self._r_passes.setValue(m.raster_passes or 1)
        self._ve_passes.setValue(m.vector_engrave_passes or 1)
        self._vc_passes.setValue(m.vector_cut_passes or 1)
        self._raster_spd.setValue(m.raster_speed or 200)
        self._ve_spd.setValue(m.vector_engrave_speed or 20)
        self._vc_spd.setValue(m.vector_cut_speed or 8)
        self._raster_pwr.setValue(m.raster_power_pct or 100)
        self._ve_pwr.setValue(m.vector_engrave_power or 100)
        self._vc_pwr.setValue(m.vector_cut_power or 16)

    # ------------------------------------------------------------------ save

    def _save(self):
        with get_session() as s:
            m = s.get(Machine, self._machine_id)
            if not m: return

            # General
            m.units               = self._units.currentText()
            m.board_type          = self._board.currentText()
            m.bed_width_mm        = self._bed_w.value()
            m.bed_height_mm       = self._bed_h.value()
            m.x_scale_factor      = self._x_scale.value()
            m.y_scale_factor      = self._y_scale.value()
            m.home_upon_initialize= self._home_on_init.isChecked()
            m.home_in_upper_right = self._home_upper_right.isChecked()
            m.wait_for_laser      = self._wait_laser.isChecked()
            m.unlock_rail_after_job=self._unlock_after.isChecked()
            m.preprocess_crc      = self._preprocess_crc.isChecked()
            m.reduce_memory       = self._reduce_mem.isChecked()
            m.max_power_pct       = self._max_power.value()

            # Raster
            m.scanline_step       = self._scanline.value()
            try: m.halftone_resolution = int(self._halftone_res.currentText())
            except ValueError: pass
            m.engrave_bottom_up   = self._engrave_bottom_up.isChecked()
            m.halftone_dither     = self._halftone_dither.isChecked()
            m.slope_black  = self._slope_black_sl.value() / 100.0 * 10.0
            m.slope_white  = self._slope_white_sl.value() / 100.0 * 2.0
            m.transition   = self._transition_sl.value() / 100.0 * 10.0

            # Rotary
            m.use_rotary          = self._use_rotary.isChecked()
            m.rotary_scale_y      = self._rotary_scale.value()
            m.rotary_rapid_speed  = self._rotary_rapid.value()

            # Advanced
            m.raster_color        = self._raster_color.isChecked()
            m.mirror_design       = self._mirror_design.isChecked()
            m.rotate_design       = self._rotate_design.isChecked()
            m.use_input_csys      = self._use_input_csys.isChecked()
            m.cut_inside_first    = self._cut_inside_first.isChecked()
            m.group_engrave_tasks = self._group_engrave.isChecked()
            m.group_vector_tasks  = self._group_vector.isChecked()
            m.raster_passes       = self._r_passes.value()
            m.vector_engrave_passes=self._ve_passes.value()
            m.vector_cut_passes   = self._vc_passes.value()
            m.raster_speed        = self._raster_spd.value()
            m.vector_engrave_speed= self._ve_spd.value()
            m.vector_cut_speed    = self._vc_spd.value()
            m.raster_power_pct    = self._raster_pwr.value()
            m.vector_engrave_power= self._ve_pwr.value()
            m.vector_cut_power    = self._vc_pwr.value()

            s.commit()

        self.accept()
