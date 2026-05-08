"""Add a product + quantity to a Job Sheet."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QComboBox, QSpinBox, QPushButton, QDialogButtonBox,
    QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt

from app.core.database import get_session, Product, JobItem, JobSheet


class AddItemDialog(QDialog):
    def __init__(self, job_sheet_id: int, parent=None):
        super().__init__(parent)
        self._job_sheet_id = job_sheet_id
        self._products: list[Product] = []
        self.setWindowTitle("Add Item to Job Sheet")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build()
        self._load_products()

    # ------------------------------------------------------------------ UI

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 20, 24, 20)

        title = QLabel("Add Product to Job")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e6edf3;")
        lay.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._product_combo = QComboBox()
        self._product_combo.setPlaceholderText("Select a product from library…")
        self._product_combo.currentIndexChanged.connect(self._on_product_changed)
        form.addRow("Product *", self._product_combo)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 9999)
        self._qty_spin.setValue(1)
        self._qty_spin.setSuffix("  units")
        self._qty_spin.valueChanged.connect(self._update_info)
        form.addRow("Quantity *", self._qty_spin)

        lay.addLayout(form)

        # Info card
        self._info_frame = QFrame()
        self._info_frame.setObjectName("Card")
        info_lay = QVBoxLayout(self._info_frame)
        info_lay.setContentsMargins(12, 10, 12, 10)
        info_lay.setSpacing(4)

        self._info_sheets = QLabel("Sheets needed: —")
        self._info_sheets.setStyleSheet("color: #d29922;")
        info_lay.addWidget(self._info_sheets)

        self._info_files = QLabel("Files per unit: —")
        self._info_files.setStyleSheet("color: #8b949e; font-size: 12px;")
        info_lay.addWidget(self._info_files)

        lay.addWidget(self._info_frame)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Add to Job Sheet")
        ok.setObjectName("PrimaryButton")
        ok.style().unpolish(ok); ok.style().polish(ok)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------ data

    def _load_products(self):
        with get_session() as s:
            self._products = s.query(Product).order_by(Product.name).all()
        self._product_combo.clear()
        for p in self._products:
            label = f"{p.name}"
            if p.sku:
                label = f"[{p.sku}]  {p.name}"
            self._product_combo.addItem(label, userData=p.id)
        self._update_info()

    def _on_product_changed(self, idx: int):
        self._update_info()

    def _update_info(self):
        idx = self._product_combo.currentIndex()
        if idx < 0 or idx >= len(self._products):
            self._info_sheets.setText("Sheets needed: —")
            self._info_files.setText("Files per unit: —")
            return
        p = self._products[idx]
        qty = self._qty_spin.value()
        sheets = p.sheets_needed(qty)
        file_count = len(p.files) if p.files else 0
        self._info_sheets.setText(
            f"Sheets needed: {sheets}  "
            f"({p.units_per_sheet} unit{'s' if p.units_per_sheet != 1 else ''} per sheet)"
        )
        self._info_files.setText(
            f"Files per unit: {file_count} file{'s' if file_count != 1 else ''} to cut"
        )

    def _save(self):
        idx = self._product_combo.currentIndex()
        if idx < 0:
            return
        product_id = self._product_combo.itemData(idx)
        qty = self._qty_spin.value()

        with get_session() as s:
            # Check if item already exists in this job sheet
            existing = (
                s.query(JobItem)
                .filter_by(job_sheet_id=self._job_sheet_id, product_id=product_id)
                .first()
            )
            if existing:
                existing.quantity_total += qty
            else:
                item = JobItem(
                    job_sheet_id=self._job_sheet_id,
                    product_id=product_id,
                    quantity_total=qty,
                )
                s.add(item)
            s.commit()

        self.accept()
