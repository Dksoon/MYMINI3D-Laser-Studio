"""Add / Edit a laser machine."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QDoubleSpinBox, QTextEdit,
    QDialogButtonBox, QFrame, QSpinBox, QPushButton, QComboBox
)
from PyQt6.QtCore import Qt

from app.core.database import get_session, Machine


class MachineDialog(QDialog):
    def __init__(self, parent=None, machine_id: Optional[int] = None):
        super().__init__(parent)
        self._machine_id = machine_id
        self.setWindowTitle("Edit Machine" if machine_id else "Add Machine")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build()
        if machine_id:
            self._load()

    # ------------------------------------------------------------------ UI

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 20, 24, 20)

        title = QLabel("Edit Machine" if self._machine_id else "Add New Machine")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#e6edf3;")
        lay.addWidget(title)

        # ── Identity ──────────────────────────────────────────────────
        id_frame = QFrame(); id_frame.setObjectName("Card")
        id_form  = QFormLayout(id_frame)
        id_form.setContentsMargins(14, 14, 14, 14)
        id_form.setSpacing(10)
        id_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Left Machine / Right Machine")
        id_form.addRow("Name *", self._name)

        lay.addWidget(id_frame)

        # ── USB identifiers ───────────────────────────────────────────
        usb_frame = QFrame(); usb_frame.setObjectName("Card")
        usb_form  = QFormLayout(usb_frame)
        usb_form.setContentsMargins(14, 14, 14, 14)
        usb_form.setSpacing(10)
        usb_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        usb_note = QLabel(
            "If you have multiple K40 machines connected, set the device number\n"
            "so each machine gets its own USB connection (0 = first, 1 = second)."
        )
        usb_note.setStyleSheet("color:#6e7681; font-size:11px;")
        usb_note.setWordWrap(True)
        usb_form.addRow("", usb_note)

        # USB device number row with Scan button
        dev_row = QHBoxLayout(); dev_row.setSpacing(8)
        self._dev_index = QSpinBox()
        self._dev_index.setRange(0, 9); self._dev_index.setValue(0)
        self._dev_index.setFixedWidth(60)
        self._dev_index.setToolTip("0 = first K40 found, 1 = second K40, etc.")
        dev_row.addWidget(self._dev_index)
        scan_btn = QPushButton("Scan")
        scan_btn.setFixedWidth(60)
        scan_btn.setToolTip("Find all connected K40 machines")
        scan_btn.clicked.connect(self._scan_devices)
        dev_row.addWidget(scan_btn)
        self._scan_lbl = QLabel("")
        self._scan_lbl.setStyleSheet("color:#6e7681; font-size:11px;")
        dev_row.addWidget(self._scan_lbl, 1)
        usb_form.addRow("USB Device #", dev_row)

        lay.addWidget(usb_frame)

        # ── Bed size ──────────────────────────────────────────────────
        bed_frame = QFrame(); bed_frame.setObjectName("Card")
        bed_form  = QFormLayout(bed_frame)
        bed_form.setContentsMargins(14, 14, 14, 14)
        bed_form.setSpacing(10)
        bed_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._bed_w = QDoubleSpinBox()
        self._bed_w.setRange(50, 1000); self._bed_w.setValue(400)
        self._bed_w.setSuffix(" mm")
        bed_form.addRow("Bed Width", self._bed_w)

        self._bed_h = QDoubleSpinBox()
        self._bed_h.setRange(50, 1000); self._bed_h.setValue(400)
        self._bed_h.setSuffix(" mm")
        bed_form.addRow("Bed Height", self._bed_h)

        lay.addWidget(bed_frame)

        # ── Notes ─────────────────────────────────────────────────────
        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Optional notes (location, quirks, etc.)")
        self._notes.setFixedHeight(60)
        lay.addWidget(self._notes)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Save Machine")
        ok.setObjectName("PrimaryButton")
        ok.style().unpolish(ok); ok.style().polish(ok)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------ data

    def _scan_devices(self):
        """Find all connected K40 USB devices and show count."""
        try:
            import usb.core
            import usb.backend.libusb0 as _lib0
            import os, sys
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            dll = None
            for d in [exe_dir, r"C:\Program Files\K40 Whisperer"]:
                p = os.path.join(d, "libusb0.dll")
                if os.path.isfile(p):
                    dll = p; break
            backend = _lib0.get_backend(find_library=lambda _: dll) if dll else None
            kwargs = {"idVendor": 0x1A86, "idProduct": 0x5512, "find_all": True}
            if backend:
                kwargs["backend"] = backend
            devices = list(usb.core.find(**kwargs))
            n = len(devices)
            if n == 0:
                self._scan_lbl.setText("No K40 found — check USB cable")
                self._scan_lbl.setStyleSheet("color:#f85149; font-size:11px;")
            else:
                self._scan_lbl.setText(
                    f"{n} K40 machine{'s' if n>1 else ''} found  "
                    f"(set 0…{n-1})"
                )
                self._scan_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
                self._dev_index.setMaximum(max(0, n - 1))
        except Exception as e:
            self._scan_lbl.setText(f"Scan error: {e}")
            self._scan_lbl.setStyleSheet("color:#f85149; font-size:11px;")

    def _load(self):
        with get_session() as s:
            m = s.get(Machine, self._machine_id)
            if not m:
                return
            self._name.setText(m.name)
            self._dev_index.setValue(m.usb_device_index or 0)
            self._bed_w.setValue(m.bed_width_mm or 400)
            self._bed_h.setValue(m.bed_height_mm or 400)
            self._notes.setPlainText(m.notes or "")

    def _save(self):
        name = self._name.text().strip()
        if not name:
            self._name.setFocus()
            self._name.setStyleSheet("border:1px solid #f85149;")
            return

        with get_session() as s:
            if self._machine_id:
                m = s.get(Machine, self._machine_id)
            else:
                m = Machine()
                s.add(m)

            m.name             = name
            m.usb_device_index = self._dev_index.value()
            m.bed_width_mm     = self._bed_w.value()
            m.bed_height_mm    = self._bed_h.value()
            m.notes            = self._notes.toPlainText().strip()
            s.flush()
            self._machine_id = m.id
            s.commit()

        self.accept()

    def saved_id(self) -> Optional[int]:
        return self._machine_id
