"""
Product File Picker — shown when user clicks a pending job item.
Displays ★ Main Files and ⚙ Part Files in separate sections.
Pre-selects based on the stored cut_type/main_file_id/part_file_ids from the job item.
User can override by clicking a different option before loading to canvas.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QRadioButton, QCheckBox,
    QButtonGroup, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.core.database import get_session, Product, ProductFile, JobItem


class ProductFilePicker(QDialog):
    """
    Shows when user clicks a pending product in the job queue.
    Signals:
      file_selected(file_path)             — load file to canvas only
      cut_requested(job_item_id, file_path) — load + open CutDialog
    """
    file_selected = pyqtSignal(str)
    cut_requested = pyqtSignal(int, str)

    def __init__(self, job_item_id: int, machine_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._job_item_id    = job_item_id
        self._machine_id     = machine_id
        self._product_name   = ""
        self._qty_pending    = 0
        self._cut_type       = "full"
        self._stored_main_id : Optional[int]  = None
        self._stored_part_ids: list[int]       = []
        self._main_files:  list[ProductFile]   = []
        self._part_files:  list[ProductFile]   = []
        self._main_radios: list[tuple[QRadioButton, int, str]] = []  # (radio, file_id, path)
        self._part_checks: list[tuple[QCheckBox, int, str]]   = []  # (cb, file_id, path)
        self.setMinimumWidth(480)
        self.setModal(True)
        self._load_data()
        self._build()

    # ------------------------------------------------------------------ data

    def _load_data(self):
        with get_session() as s:
            item = s.get(JobItem, self._job_item_id)
            if item and item.product:
                p = item.product
                self._product_name   = p.name
                self._main_files     = list(p.main_files)
                self._part_files     = list(p.part_files)
                self._qty_pending    = item.quantity_pending
                self._cut_type       = item.cut_type or "full"
                self._stored_main_id = item.main_file_id
                try:
                    self._stored_part_ids = json.loads(item.part_file_ids or "[]")
                except Exception:
                    self._stored_part_ids = []
        self.setWindowTitle(f"Files — {self._product_name}")

    # ------------------------------------------------------------------ UI

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 14, 16, 14)

        # Header
        name_lbl = QLabel(self._product_name)
        name_lbl.setStyleSheet("font-size:15px; font-weight:bold; color:#e6edf3;")
        root.addWidget(name_lbl)

        # Pending qty + stored cut type badge
        info_row = QHBoxLayout()
        info_row.setSpacing(10)
        pend_lbl = QLabel(f"Pending: {self._qty_pending} unit(s)")
        pend_lbl.setStyleSheet("color:#d29922; font-size:12px;")
        info_row.addWidget(pend_lbl)

        if self._cut_type == "full":
            badge = QLabel("★ Full Sheet cut")
            badge.setStyleSheet(
                "color:#3fb950; background:#1a2d1a; border:1px solid #2ea043;"
                "border-radius:3px; padding:2px 8px; font-size:11px;"
            )
        else:
            badge = QLabel("⚙ Individual Parts cut")
            badge.setStyleSheet(
                "color:#58a6ff; background:#0d1f38; border:1px solid #1f6feb;"
                "border-radius:3px; padding:2px 8px; font-size:11px;"
            )
        info_row.addWidget(badge)
        info_row.addStretch()
        root.addLayout(info_row)

        # Scrollable file sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_w = QWidget()
        scroll_w.setStyleSheet("background:#0d1117;")
        s_lay = QVBoxLayout(scroll_w)
        s_lay.setContentsMargins(0, 4, 0, 4)
        s_lay.setSpacing(8)

        # ── ★ Main Files ──────────────────────────────────────────────
        if self._main_files:
            main_hdr = QLabel("★  MAIN FILES")
            main_hdr.setStyleSheet(
                "color:#3fb950; font-size:10px; font-weight:bold;"
                "letter-spacing:1px; padding:0;"
            )
            s_lay.addWidget(main_hdr)

            radio_group = QButtonGroup(self)
            for f in self._main_files:
                path = f.file_path or ""
                exists = Path(path).exists() if path else False
                fname = Path(path).name if path else "(no file)"
                sheet_n = f.sheet_number or 1
                label = f"Sheet {sheet_n}: {fname}"
                if not exists:
                    label += "  ⚠ missing"

                radio = QRadioButton(label)
                radio.setStyleSheet(
                    "color:#e6edf3; font-size:11px; border:none; padding:4px 2px;"
                    if exists else
                    "color:#f85149; font-size:11px; border:none; padding:4px 2px;"
                )
                # Pre-select stored main file
                if self._cut_type == "full" and f.id == self._stored_main_id:
                    radio.setChecked(True)
                radio_group.addButton(radio)
                s_lay.addWidget(radio)
                self._main_radios.append((radio, f.id, path))

            # If none pre-selected, select first
            if self._cut_type == "full" and not any(r.isChecked() for r, _, _ in self._main_radios):
                if self._main_radios:
                    self._main_radios[0][0].setChecked(True)
        else:
            no_main = QLabel("No main files attached to this product.")
            no_main.setStyleSheet("color:#484f58; font-size:11px; padding:4px;")
            s_lay.addWidget(no_main)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background:#21262d; max-height:1px; margin:4px 0;")
        s_lay.addWidget(div)

        # ── ⚙ Part Files ──────────────────────────────────────────────
        if self._part_files:
            part_hdr = QLabel("⚙  PART FILES")
            part_hdr.setStyleSheet(
                "color:#58a6ff; font-size:10px; font-weight:bold;"
                "letter-spacing:1px; padding:0;"
            )
            s_lay.addWidget(part_hdr)

            for f in self._part_files:
                path = f.file_path or ""
                exists = Path(path).exists() if path else False
                name = f.part_name or Path(path).name if path else "(no file)"
                if not exists:
                    name += "  ⚠ missing"

                cb = QCheckBox(name)
                cb.setStyleSheet(
                    "color:#e6edf3; font-size:11px; border:none; padding:3px 2px;"
                    if exists else
                    "color:#f85149; font-size:11px; border:none; padding:3px 2px;"
                )
                # Pre-check stored parts
                if self._cut_type == "parts" and f.id in self._stored_part_ids:
                    cb.setChecked(True)
                s_lay.addWidget(cb)
                self._part_checks.append((cb, f.id, path))
        else:
            no_parts = QLabel("No part files attached to this product.")
            no_parts.setStyleSheet("color:#484f58; font-size:11px; padding:4px;")
            s_lay.addWidget(no_parts)

        s_lay.addStretch()
        scroll.setWidget(scroll_w)
        root.addWidget(scroll, 1)

        # Hint
        hint = QLabel("Click 'Load to Canvas' to preview a file. 'Start Cut' uses the stored selection.")
        hint.setStyleSheet("color:#484f58; font-size:10px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()

        load_btn = QPushButton("Load to Canvas")
        load_btn.setFixedHeight(30)
        load_btn.setStyleSheet(
            "background:#1a2e4a; color:#58a6ff; border:1px solid #1f6feb;"
            "border-radius:4px; font-weight:bold; min-height:0; max-height:30px;"
        )
        load_btn.clicked.connect(self._load_only)
        btn_row.addWidget(load_btn)

        cut_btn = QPushButton("Load + Start Cut  ✂")
        cut_btn.setFixedHeight(30)
        cut_btn.setStyleSheet(
            "background:#9e6a03; color:#fff; border:1px solid #d29922;"
            "border-radius:4px; font-weight:bold; min-height:0; max-height:30px;"
        )
        cut_btn.setEnabled(self._qty_pending > 0)
        cut_btn.clicked.connect(self._load_and_cut)
        btn_row.addWidget(cut_btn)

        root.addLayout(btn_row)

    # ------------------------------------------------------------------ helpers

    def _canvas_load_path(self) -> Optional[str]:
        """Return the path of the file the user has selected for canvas preview."""
        # Priority: checked radio (main), then first checked part
        for radio, fid, path in self._main_radios:
            if radio.isChecked() and path and Path(path).exists():
                return path
        for cb, fid, path in self._part_checks:
            if cb.isChecked() and path and Path(path).exists():
                return path
        return None

    def _cut_file_path(self) -> Optional[str]:
        """Return representative file path for the cut_requested signal."""
        # For canvas load — use stored main or first part
        if self._cut_type == "full":
            for radio, fid, path in self._main_radios:
                if radio.isChecked():
                    return path if path else None
        else:
            for cb, fid, path in self._part_checks:
                if cb.isChecked():
                    return path if path else None
        return None

    # ------------------------------------------------------------------ actions

    def _load_only(self):
        path = self._canvas_load_path()
        if path:
            self.file_selected.emit(path)
            self.accept()
        else:
            QMessageBox.warning(self, "No File",
                "No file selected or file is missing.")

    def _load_and_cut(self):
        path = self._cut_file_path() or ""
        if path:
            self.file_selected.emit(path)
        self.cut_requested.emit(self._job_item_id, path)
        self.accept()
