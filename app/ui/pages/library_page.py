from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QMessageBox, QButtonGroup,
    QFileDialog, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer

from app.core.database import get_session, Product
from app.ui.dialogs.add_product_dialog import AddProductDialog


# ─────────────────────────────────────────────────────────────
# Product Card — name + category only, no files
# ─────────────────────────────────────────────────────────────

class ProductCard(QFrame):
    def __init__(self, product: Product, parent=None):
        super().__init__(parent)
        self.product_id = product.id
        self.setFixedHeight(46)
        self.setStyleSheet(
            "background:#1c2128; border:1px solid #30363d; border-radius:6px;"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build(product)

    def _build(self, p: Product):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)

        name = QLabel(p.name)
        name.setStyleSheet(
            "color:#e6edf3; font-weight:bold; font-size:13px;"
            "background:transparent; border:none;"
        )
        lay.addWidget(name, 1)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(26)
        edit_btn.setMinimumWidth(44)
        edit_btn.setToolTip("Edit product")
        edit_btn.setStyleSheet(
            "background:#21262d; color:#e6edf3; border:1px solid #444c56;"
            "border-radius:4px; font-size:11px; min-height:0; max-height:26px;"
        )
        edit_btn.clicked.connect(lambda: self._action("edit"))
        lay.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Delete product")
        del_btn.setStyleSheet(
            "background:transparent; color:#f85149; border:1px solid #30363d;"
            "border-radius:4px; font-size:12px; min-height:0;"
        )
        del_btn.clicked.connect(lambda: self._action("delete"))
        lay.addWidget(del_btn)

    def _action(self, action: str):
        p = self.parent()
        while p and not isinstance(p, LibraryPage):
            p = p.parent()
        if p:
            if action == "edit":
                p._edit_product(self.product_id)
            else:
                p._delete_product(self.product_id)

    def mouseDoubleClickEvent(self, event):
        self._action("edit")


# ─────────────────────────────────────────────────────────────
# Category Section
# ─────────────────────────────────────────────────────────────

class CategorySection(QWidget):
    def __init__(self, category: str, parent=None):
        super().__init__(parent)
        self._category  = category
        self._cards: list[ProductCard] = []
        self._collapsed = False
        self._build()

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 4)
        self._root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(
            "background:#161b22; border-top:1px solid #30363d;"
            "border-bottom:1px solid #30363d;"
        )
        hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 6, 14, 6)
        hl.setSpacing(8)

        self._toggle = QPushButton("▼")
        self._toggle.setFixedSize(18, 18)
        self._toggle.setStyleSheet(
            "color:#6e7681; background:transparent; border:none; font-size:9px; padding:0;"
        )
        self._toggle.clicked.connect(self._do_toggle)
        hl.addWidget(self._toggle)

        self._cat_lbl = QLabel(self._category or "Uncategorized")
        self._cat_lbl.setStyleSheet(
            "color:#e6edf3; font-weight:bold; font-size:12px; border:none; background:transparent;"
        )
        hl.addWidget(self._cat_lbl, 1)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(
            "color:#6e7681; font-size:11px; border:none; background:transparent;"
        )
        hl.addWidget(self._count_lbl)

        rename_btn = QPushButton("✎ Rename")
        rename_btn.setFixedHeight(22)
        rename_btn.setStyleSheet(
            "background:#21262d; color:#8b949e; border:1px solid #30363d;"
            "border-radius:3px; font-size:10px; min-height:0; max-height:22px; padding:0 6px;"
        )
        rename_btn.clicked.connect(self._rename_category)
        hl.addWidget(rename_btn)

        hdr.mousePressEvent = lambda e: self._do_toggle()
        self._root.addWidget(hdr)

        # Cards container
        self._body = QWidget()
        self._body.setStyleSheet("background:#0d1117;")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(20, 6, 20, 6)
        self._body_lay.setSpacing(4)
        self._root.addWidget(self._body)

    def _do_toggle(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._toggle.setText("▶" if self._collapsed else "▼")

    def _rename_category(self):
        old_name = self._category or "Uncategorized"
        new_name, ok = QInputDialog.getText(
            self, "Rename Category",
            f"New name for  '{old_name}':",
            text=old_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        # Update all products in this category
        with get_session() as s:
            prods = s.query(Product).filter(Product.category == self._category).all()
            for p in prods:
                p.category = new_name
            s.commit()
        # Refresh the library page
        lib = self.parent()
        while lib and not isinstance(lib, LibraryPage):
            lib = lib.parent()
        if lib:
            lib.refresh()

    def add_card(self, card: ProductCard):
        self._cards.append(card)
        self._body_lay.addWidget(card)
        self._count_lbl.setText(f"{len(self._cards)} product{'s' if len(self._cards)!=1 else ''}")

    def clear_cards(self):
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()


# ─────────────────────────────────────────────────────────────
# Library Page
# ─────────────────────────────────────────────────────────────

class LibraryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self._sections: list[CategorySection] = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame(); header.setObjectName("HeaderBar")
        h = QHBoxLayout(header); h.setContentsMargins(24, 16, 24, 12)
        tc = QVBoxLayout()
        t = QLabel("Library"); t.setObjectName("PageTitle"); tc.addWidget(t)
        s = QLabel("Product catalogue — organised by category")
        s.setObjectName("PageSubtitle"); tc.addWidget(s)
        h.addLayout(tc); h.addStretch()

        imp_btn = QPushButton("↑ Import Excel")
        imp_btn.setFixedHeight(32)
        imp_btn.setStyleSheet(
            "background:#1a2e4a; color:#58a6ff; border:1px solid #1f6feb;"
            "border-radius:4px; font-weight:bold; font-size:11px;"
            "min-height:0; max-height:32px;"
        )
        imp_btn.clicked.connect(self._import_excel)
        h.addWidget(imp_btn)

        add_btn = QPushButton("+ Add Product")
        add_btn.setObjectName("PrimaryButton")
        add_btn.style().unpolish(add_btn); add_btn.style().polish(add_btn)
        add_btn.clicked.connect(self._add_product)
        h.addWidget(add_btn)
        root.addWidget(header)

        # Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("background:#161b22; border-bottom:1px solid #21262d;")
        tlay = QHBoxLayout(toolbar)
        tlay.setContentsMargins(24, 10, 24, 10); tlay.setSpacing(12)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search products…")
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self._on_search)
        tlay.addWidget(self._search)
        tlay.addStretch()
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#6e7681; font-size:12px;")
        tlay.addWidget(self._count_lbl)
        root.addWidget(toolbar)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget(); self._content.setStyleSheet("background:#0d1117;")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(0, 0, 0, 24)
        self._content_lay.setSpacing(0)
        self._content_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

    # ------------------------------------------------------------------ data

    def refresh(self):
        self._clear()
        with get_session() as s:
            products = (
                s.query(Product)
                .order_by(Product.category, Product.name)
                .all()
            )

        term = self._search_text.lower()
        filtered = [
            p for p in products
            if not term or term in p.name.lower() or term in (p.category or "").lower()
        ]

        self._count_lbl.setText(
            f"{len(filtered)} product{'s' if len(filtered)!=1 else ''}"
        )

        if not filtered:
            lbl = QLabel(
                "No products yet. Click '+ Add Product' or '↑ Import Excel'."
                if not term else f"No products match '{term}'."
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:#6e7681; font-size:13px; padding:40px;")
            self._content_lay.addWidget(lbl)
            return

        from collections import OrderedDict
        groups: OrderedDict[str, list[Product]] = OrderedDict()
        for p in filtered:
            groups.setdefault(p.category or "", []).append(p)

        for cat, prods in groups.items():
            section = CategorySection(cat)
            for p in prods:
                card = ProductCard(p)
                section.add_card(card)
            self._content_lay.addWidget(section)
            self._sections.append(section)

        self._content_lay.addStretch(1)

    def _clear(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sections.clear()

    # ------------------------------------------------------------------ events

    def _on_search(self, text: str):
        self._search_text = text
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    # ------------------------------------------------------------------ actions

    def _add_product(self):
        dlg = AddProductDialog(self)
        if dlg.exec():
            self.refresh()

    def _edit_product(self, product_id: int):
        dlg = AddProductDialog(self, product_id=product_id)
        if dlg.exec():
            self.refresh()

    def _delete_product(self, product_id: int):
        with get_session() as s:
            p = s.get(Product, product_id)
            name = p.name if p else "this product"
        reply = QMessageBox.question(
            self, "Delete Product", f"Delete <b>{name}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            with get_session() as s:
                p = s.get(Product, product_id)
                if p:
                    s.delete(p)
                    s.commit()
            self.refresh()

    # ------------------------------------------------------------------ Excel import

    def _import_excel(self):
        # Default: look for PRODUCT LIST.xlsx next to the app
        default_path = str(
            Path(__file__).parent.parent.parent.parent / "PRODUCT LIST.xlsx"
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Product List Excel",
            default_path if Path(default_path).exists() else "",
            "Excel Files (*.xlsx *.xls)"
        )
        if not path:
            return

        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Could not read Excel:\n{e}")
            return

        # Find header row (contains "Product Name")
        start = 0
        for i, row in enumerate(rows):
            if any(str(c).strip().lower() == "product name" for c in row if c):
                start = i + 1
                break

        candidates = []
        for row in rows[start:]:
            name = str(row[0]).strip() if row[0] else ""
            cat  = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            if name and cat and name.lower() != "none":
                candidates.append((name, cat))

        if not candidates:
            QMessageBox.warning(self, "No Data",
                "No product rows found.\n"
                "Expected columns: Product Name | CAT.")
            return

        # Insert missing products
        added = skipped = 0
        with get_session() as s:
            existing = {
                (p.name.strip().lower(), (p.category or "").strip().lower())
                for p in s.query(Product).all()
            }
            for name, cat in candidates:
                key = (name.lower(), cat.lower())
                if key in existing:
                    skipped += 1
                else:
                    s.add(Product(name=name, category=cat))
                    existing.add(key)
                    added += 1
            s.commit()

        self.refresh()
        QMessageBox.information(
            self, "Import Complete",
            f"Imported {added} new product{'s' if added!=1 else ''}.\n"
            f"{skipped} already existed — skipped."
        )
