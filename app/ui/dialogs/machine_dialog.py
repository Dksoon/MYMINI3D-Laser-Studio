"""Add / Edit a laser machine."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QDoubleSpinBox, QTextEdit,
    QDialogButtonBox, QFrame
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
        self._name.setPlaceholderText("e.g. Laser #1")
        id_form.addRow("Name *", self._name)

        self._serial = QLineEdit()
        self._serial.setPlaceholderText("Leave blank if only one K40 is connected")
        id_form.addRow("Serial Number", self._serial)

        lay.addWidget(id_frame)

        # ── USB identifiers ───────────────────────────────────────────
        usb_frame = QFrame(); usb_frame.setObjectName("Card")
        usb_form  = QFormLayout(usb_frame)
        usb_form.setContentsMargins(14, 14, 14, 14)
        usb_form.setSpacing(10)
        usb_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        usb_note = QLabel(
            "K40 defaults: Vendor 1a86 · Product 5512\n"
            "Change only if your machine uses different USB IDs."
        )
        usb_note.setStyleSheet("color:#6e7681; font-size:11px;")
        usb_note.setWordWrap(True)
        usb_form.addRow("", usb_note)

        self._vendor = QLineEdit("1a86")
        self._vendor.setMaxLength(6)
        usb_form.addRow("Vendor ID (hex)", self._vendor)

        self._product_id_edit = QLineEdit("5512")
        self._product_id_edit.setMaxLength(6)
        usb_form.addRow("Product ID (hex)", self._product_id_edit)

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

    def _load(self):
        with get_session() as s:
            m = s.get(Machine, self._machine_id)
            if not m:
                return
            self._name.setText(m.name)
            self._serial.setText(m.serial_number or "")
            self._vendor.setText(m.usb_vendor_id or "1a86")
            self._product_id_edit.setText(m.usb_product_id or "5512")
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
            m.serial_number    = self._serial.text().strip()
            m.usb_vendor_id    = self._vendor.text().strip().lower() or "1a86"
            m.usb_product_id   = self._product_id_edit.text().strip().lower() or "5512"
            m.bed_width_mm     = self._bed_w.value()
            m.bed_height_mm    = self._bed_h.value()
            m.notes            = self._notes.toPlainText().strip()
            s.flush()
            self._machine_id = m.id
            s.commit()

        self.accept()

    def saved_id(self) -> Optional[int]:
        return self._machine_id
