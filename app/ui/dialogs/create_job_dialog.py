"""New Job creation dialog — product + quantity, auto-merges duplicates."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QSpinBox,
    QFrame, QSplitter, QWidget, QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt

from app.core.database import get_session, Product, JobSheet, JobItem, JobSheetStatus


class CreateJobDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Job")
        self.setMinimumSize(870, 644)
        self.setModal(True)
        self._products: list[Product] = []
        self._job_items: dict[int, int] = {}   # product_id → qty (merged)
        self._saved_id: Optional[int] = None
        self._build()
        self._load_products()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 14, 16, 14)

        title = QLabel("Create New Job")
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#e6edf3;")
        root.addWidget(title)

        hint = QLabel("Search and add products. Same product added twice will merge quantities.")
        hint.setStyleSheet("color:#8b949e; font-size:11px;")
        root.addWidget(hint)

        split = QSplitter(Qt.Orientation.Horizontal)

        # Left — product search
        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 6, 0); ll.setSpacing(6)

        ll.addWidget(QLabel("PRODUCT LIBRARY").also(
            lambda l: l.setStyleSheet(
                "color:#6e7681; font-size:10px; font-weight:bold; letter-spacing:1px;"
            )
        ))

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search product name…")
        self._search.textChanged.connect(self._filter)
        ll.addWidget(self._search)

        self._product_list = QListWidget()
        self._product_list.setStyleSheet(
            "QListWidget::item{padding:8px; border-bottom:1px solid #21262d;}"
            "QListWidget::item:selected{background:#1f3a5f;}"
        )
        self._product_list.itemDoubleClicked.connect(self._quick_add)
        ll.addWidget(self._product_list, 1)

        add_row = QHBoxLayout(); add_row.setSpacing(6)
        add_row.addWidget(QLabel("Qty:").also(
            lambda l: l.setStyleSheet("color:#8b949e; font-size:11px;")))
        self._qty = QSpinBox()
        self._qty.setRange(1, 9999); self._qty.setValue(1); self._qty.setFixedWidth(90)
        add_row.addWidget(self._qty)
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet(
            "background:#1f6feb; color:#fff; border:none; border-radius:4px;"
            "font-weight:bold; min-height:0; max-height:28px;"
        )
        add_btn.clicked.connect(self._add_selected)
        add_row.addWidget(add_btn, 1)
        ll.addLayout(add_row)
        split.addWidget(left)

        # Right — job list
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(6, 0, 0, 0); rl.setSpacing(6)
        rl.addWidget(QLabel("JOB ITEMS").also(
            lambda l: l.setStyleSheet(
                "color:#6e7681; font-size:10px; font-weight:bold; letter-spacing:1px;"
            )
        ))
        self._job_list = QListWidget()
        self._job_list.setStyleSheet(
            "QListWidget::item{padding:8px; border-bottom:1px solid #21262d;}"
        )
        rl.addWidget(self._job_list, 1)
        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedHeight(24)
        clear_btn.setStyleSheet(
            "color:#f85149; background:transparent; border:none; font-size:11px;"
        )
        clear_btn.clicked.connect(self._clear)
        rl.addWidget(clear_btn)
        split.addWidget(right)

        split.setSizes([310, 280])
        root.addWidget(split, 1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()

        self._total_lbl = QLabel("0 items")
        self._total_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        btn_row.addWidget(self._total_lbl)

        self._create_btn = QPushButton("Create Job")
        self._create_btn.setFixedHeight(32)
        self._create_btn.setStyleSheet(
            "background:#238636; color:#fff; border:none; border-radius:4px;"
            "font-size:13px; font-weight:bold; min-height:0; max-height:32px;"
        )
        self._create_btn.setEnabled(False)
        self._create_btn.clicked.connect(self._create_job)
        btn_row.addWidget(self._create_btn)
        root.addLayout(btn_row)

    def _load_products(self):
        with get_session() as s:
            self._products = (
                s.query(Product).order_by(Product.category, Product.name).all()
            )
        self._filter("")

    def _filter(self, text: str = ""):
        term = (text or self._search.text()).lower()
        self._product_list.clear()
        for p in self._products:
            if term and term not in p.name.lower() and term not in (p.category or "").lower():
                continue
            cat = f"[{p.category}]  " if p.category else ""
            item = QListWidgetItem(f"{cat}{p.name}")
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            self._product_list.addItem(item)

    def _quick_add(self, item: QListWidgetItem):
        self._merge(item.data(Qt.ItemDataRole.UserRole), 1)

    def _add_selected(self):
        items = self._product_list.selectedItems()
        if not items:
            return
        self._merge(items[0].data(Qt.ItemDataRole.UserRole), self._qty.value())
        self._qty.setValue(1)

    def _merge(self, product_id: int, qty: int):
        self._job_items[product_id] = self._job_items.get(product_id, 0) + qty
        self._refresh_list()

    def _refresh_list(self):
        self._job_list.clear()
        product_map = {p.id: p for p in self._products}
        total = sum(self._job_items.values())
        for pid, qty in self._job_items.items():
            p = product_map.get(pid)
            if not p:
                continue
            cat = f"[{p.category}]  " if p.category else ""
            item = QListWidgetItem(f"{cat}{p.name}  ×{qty}")
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self._job_list.addItem(item)
        self._total_lbl.setText(
            f"{len(self._job_items)} product{'s' if len(self._job_items)!=1 else ''}"
            f",  {total} unit{'s' if total!=1 else ''} total"
        )
        self._create_btn.setEnabled(bool(self._job_items))

    def _clear(self):
        self._job_items.clear()
        self._refresh_list()

    def _create_job(self):
        if not self._job_items:
            return
        name = f"Job {datetime.now().strftime('%Y-%m-%d  %H:%M')}"
        with get_session() as s:
            sheet = JobSheet(name=name, status=JobSheetStatus.open)
            s.add(sheet); s.flush()
            for pid, qty in self._job_items.items():
                s.add(JobItem(
                    job_sheet_id=sheet.id,
                    product_id=pid,
                    quantity_total=qty,
                ))
            s.commit()
            self._saved_id = sheet.id
        self.accept()

    def saved_id(self) -> Optional[int]:
        return self._saved_id


# Patch .also()
from PyQt6.QtWidgets import QWidget as _QW
if not hasattr(_QW, "also"):
    def _also(self, fn): fn(self); return self
    _QW.also = _also
