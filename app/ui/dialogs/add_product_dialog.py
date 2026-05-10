"""Add / Edit Product — Category + Name + Folder path."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QFrame, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt

from app.core.database import get_session, Product


def _db_categories() -> list[str]:
    """Get distinct category names from the database."""
    with get_session() as s:
        rows = (
            s.query(Product.category)
            .filter(Product.category != None, Product.category != "")
            .distinct()
            .order_by(Product.category)
            .all()
        )
    return [r[0] for r in rows]


class AddProductDialog(QDialog):

    def __init__(self, parent=None, product_id: Optional[int] = None):
        super().__init__(parent)
        self._product_id = product_id
        self._saved_id: Optional[int] = None
        self.setWindowTitle("Edit Product" if product_id else "Add New Product")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build()
        if product_id:
            self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 18, 20, 16)

        title = QLabel("Edit Product" if self._product_id else "Add New Product")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#e6edf3;")
        root.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet(
            "background:#1c2128; border:1px solid #30363d; border-radius:6px;"
        )
        flay = QVBoxLayout(frame)
        flay.setContentsMargins(14, 14, 14, 14)
        flay.setSpacing(10)

        # Category
        cat_row = QHBoxLayout(); cat_row.setSpacing(8)
        cat_lbl = QLabel("Category *")
        cat_lbl.setFixedWidth(110)
        cat_lbl.setStyleSheet("color:#c9d1d9; font-size:12px;")
        cat_row.addWidget(cat_lbl)
        self._category = QComboBox()
        self._category.setEditable(True)
        self._category.setPlaceholderText("Select or type new…")
        self._category.addItems(_db_categories())
        cat_row.addWidget(self._category, 1)
        flay.addLayout(cat_row)

        # Product Name
        name_row = QHBoxLayout(); name_row.setSpacing(8)
        name_lbl = QLabel("Product Name *")
        name_lbl.setFixedWidth(110)
        name_lbl.setStyleSheet("color:#c9d1d9; font-size:12px;")
        name_row.addWidget(name_lbl)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. B KAIDO TALL V3")
        name_row.addWidget(self._name, 1)
        flay.addLayout(name_row)

        # Folder path
        folder_row = QHBoxLayout(); folder_row.setSpacing(8)
        folder_lbl = QLabel("Folder")
        folder_lbl.setFixedWidth(110)
        folder_lbl.setStyleSheet("color:#c9d1d9; font-size:12px;")
        folder_row.addWidget(folder_lbl)
        self._folder = QLineEdit()
        self._folder.setPlaceholderText("Browse to set the OneDrive folder for this product…")
        self._folder.setReadOnly(True)
        self._folder.setStyleSheet("color:#8b949e; font-size:11px;")
        folder_row.addWidget(self._folder, 1)
        browse_btn = QPushButton("📁 Browse")
        browse_btn.setFixedHeight(28)
        browse_btn.setStyleSheet(
            "background:#21262d; color:#e6edf3; border:1px solid #444c56;"
            "border-radius:4px; font-size:11px; min-height:0; max-height:28px; padding:0 8px;"
        )
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        flay.addLayout(folder_row)

        root.addWidget(frame)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        save = QPushButton("Save")
        save.setFixedHeight(32)
        save.setStyleSheet(
            "background:#238636; color:#fff; border:none; border-radius:4px;"
            "font-size:12px; font-weight:bold; min-height:0; max-height:32px;"
        )
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        root.addLayout(btn_row)

    def _browse_folder(self):
        start = self._folder.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Select Product Folder", start
        )
        if folder:
            self._folder.setText(folder)

    def _load(self):
        with get_session() as s:
            p = s.get(Product, self._product_id)
            if p:
                self._category.setCurrentText(p.category or "")
                self._name.setText(p.name)
                self._folder.setText(p.folder_path or "")

    def _save(self):
        name = self._name.text().strip()
        cat  = self._category.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a product name.")
            return
        if not cat:
            QMessageBox.warning(self, "Missing Category", "Enter a category.")
            return
        try:
            with get_session() as s:
                if self._product_id:
                    p = s.get(Product, self._product_id)
                    if not p:
                        p = Product(name=name, category=cat)
                        s.add(p)
                    else:
                        p.name = name
                        p.category = cat
                        p.folder_path = self._folder.text().strip()
                        p.updated_at = datetime.utcnow()
                else:
                    p = Product(name=name, category=cat,
                                folder_path=self._folder.text().strip())
                    s.add(p)
                s.flush()
                self._saved_id = p.id
                s.commit()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            return
        self.accept()

    def saved_id(self) -> Optional[int]:
        return self._saved_id
