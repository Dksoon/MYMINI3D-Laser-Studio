from __future__ import annotations
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSplitter, QListWidget, QListWidgetItem,
    QProgressBar, QMessageBox, QMenu, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from app.core.database import (
    get_session, JobSheet, JobSheetStatus, JobItem,
    JobRun, RunStatus, Machine, MachineStatus
)
from app.ui.dialogs.job_sheet_dialog import JobSheetDialog
from app.ui.dialogs.add_item_dialog import AddItemDialog
from app.ui.dialogs.cut_dialog import CutDialog, CompleteRunDialog


# ─────────────────────────────────────────────────────────────────────
# Left panel — Job Sheet list
# ─────────────────────────────────────────────────────────────────────

STATUS_COLOR = {
    JobSheetStatus.open:        "#58a6ff",
    JobSheetStatus.in_progress: "#d29922",
    JobSheetStatus.completed:   "#3fb950",
    JobSheetStatus.archived:    "#6e7681",
}

STATUS_BADGE = {
    JobSheetStatus.open:        "BadgeBlue",
    JobSheetStatus.in_progress: "BadgeYellow",
    JobSheetStatus.completed:   "BadgeGreen",
    JobSheetStatus.archived:    "SidebarVersion",
}


class SheetListItem(QWidget):
    def __init__(self, sheet: JobSheet, parent=None):
        super().__init__(parent)
        self.sheet_id = sheet.id
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {STATUS_COLOR.get(sheet.status,'#6e7681')}; font-size: 11px;")
        dot.setFixedWidth(14)
        top.addWidget(dot)

        name = QLabel(sheet.name)
        name.setStyleSheet("color: #e6edf3; font-weight: bold; font-size: 13px;")
        name.setWordWrap(False)
        top.addWidget(name, 1)
        lay.addLayout(top)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(sheet.progress_pct))
        bar.setFixedHeight(4)
        lay.addWidget(bar)

        bottom = QHBoxLayout()
        pct_lbl = QLabel(f"{sheet.progress_pct:.0f}%")
        pct_lbl.setStyleSheet("color: #6e7681; font-size: 11px;")
        bottom.addWidget(pct_lbl)
        bottom.addStretch()
        items_lbl = QLabel(f"{sheet.completed_items}/{sheet.total_items} pcs")
        items_lbl.setStyleSheet("color: #6e7681; font-size: 11px;")
        bottom.addWidget(items_lbl)
        lay.addLayout(bottom)


# ─────────────────────────────────────────────────────────────────────
# Right panel — detail + items
# ─────────────────────────────────────────────────────────────────────

class ItemRow(QFrame):
    """One job item row in the detail panel."""
    cut_requested    = pyqtSignal(int)   # job_item_id
    delete_requested = pyqtSignal(int)   # job_item_id

    def __init__(self, item: JobItem, parent=None):
        super().__init__(parent)
        self.item_id = item.id
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build(item)

    def _build(self, item: JobItem):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        # Product info
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        p = item.product
        prod_name = p.name if p else "Unknown"
        sku = f"  [{p.sku}]" if p and p.sku else ""
        name_lbl = QLabel(f"{prod_name}{sku}")
        name_lbl.setStyleSheet("font-weight: bold; color: #e6edf3;")
        info_col.addWidget(name_lbl)

        file_count = len(p.files) if p else 0
        ups = p.units_per_sheet if p else 1
        detail = QLabel(f"{file_count} file{'s' if file_count!=1 else ''} per unit  ·  {ups} unit{'s' if ups!=1 else ''}/sheet")
        detail.setStyleSheet("color: #6e7681; font-size: 11px;")
        info_col.addWidget(detail)
        lay.addLayout(info_col, 3)

        # Qty columns
        def qty_col(label: str, value: int, color: str):
            col = QVBoxLayout()
            col.setSpacing(1)
            col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v_lbl = QLabel(str(value))
            v_lbl.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t_lbl = QLabel(label)
            t_lbl.setStyleSheet("color: #6e7681; font-size: 10px;")
            t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(v_lbl)
            col.addWidget(t_lbl)
            return col

        lay.addLayout(qty_col("PENDING",     item.quantity_pending,     "#e6edf3"), 1)
        lay.addLayout(qty_col("IN PROGRESS", item.quantity_in_progress, "#d29922"), 1)
        lay.addLayout(qty_col("DONE",        item.quantity_completed,   "#3fb950"), 1)

        # Sheets needed
        pending = item.quantity_pending
        if pending > 0:
            sheets = p.sheets_needed(pending) if p else 0
            sh_lbl = QLabel(f"{sheets}\nsheets")
            sh_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sh_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
            lay.addWidget(sh_lbl)

        # Actions
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        if pending > 0:
            cut_btn = QPushButton("✂  Cut")
            cut_btn.setObjectName("CutButton")
            cut_btn.setFixedHeight(32)
            cut_btn.style().unpolish(cut_btn); cut_btn.style().polish(cut_btn)
            cut_btn.clicked.connect(lambda: self.cut_requested.emit(self.item_id))
            btn_col.addWidget(cut_btn)

        del_btn = QPushButton("✕")
        del_btn.setToolTip("Remove item from job sheet")
        del_btn.setFixedHeight(28)
        del_btn.setFixedWidth(32)
        del_btn.setStyleSheet("color: #6e7681; background: transparent; border: none;")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.item_id))
        btn_col.addWidget(del_btn)

        lay.addLayout(btn_col)


class InProgressRow(QFrame):
    """One 'in-progress' run row shown at the bottom of the detail panel."""
    action_requested = pyqtSignal(int)   # run_id

    def __init__(self, run: JobRun, parent=None):
        super().__init__(parent)
        self.run_id = run.id
        self.setObjectName("Card")
        self.setStyleSheet("#Card { border: 1px solid #9e6a03; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        pulse = QLabel("◉")
        pulse.setStyleSheet("color: #d29922; font-size: 16px;")
        lay.addWidget(pulse)

        item = run.job_item
        product_name = item.product.name if item and item.product else "Unknown"
        machine_name = run.machine.name if run.machine else "—"
        info = QLabel(f"<b>{product_name}</b>  ×{run.quantity}   →   {machine_name}")
        info.setStyleSheet("color: #e6edf3;")
        lay.addWidget(info, 1)

        started = run.started_at
        if started:
            elapsed_min = int((datetime.utcnow() - started).total_seconds() / 60)
            time_lbl = QLabel(f"{elapsed_min}m ago")
            time_lbl.setStyleSheet("color: #6e7681; font-size: 11px;")
            lay.addWidget(time_lbl)

        action_btn = QPushButton("Done / Cancel")
        action_btn.setFixedHeight(30)
        action_btn.clicked.connect(lambda: self.action_requested.emit(self.run_id))
        lay.addWidget(action_btn)


# ─────────────────────────────────────────────────────────────────────
# Main Job Sheets Page
# ─────────────────────────────────────────────────────────────────────

class JobSheetsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_sheet_id: Optional[int] = None
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_detail)
        self._timer.start(10000)

    # ------------------------------------------------------------------ layout

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("HeaderBar")
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 16, 24, 12)

        title_col = QVBoxLayout()
        title = QLabel("Job Sheets")
        title.setObjectName("PageTitle")
        title_col.addWidget(title)
        sub = QLabel("Track production jobs, quantities and progress")
        sub.setObjectName("PageSubtitle")
        title_col.addWidget(sub)
        h.addLayout(title_col)
        h.addStretch()

        new_btn = QPushButton("+ New Job Sheet")
        new_btn.setObjectName("PrimaryButton")
        new_btn.style().unpolish(new_btn); new_btn.style().polish(new_btn)
        new_btn.clicked.connect(self._new_sheet)
        h.addWidget(new_btn)
        root.addWidget(header)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)

        # Left: sheet list
        left = QWidget()
        left.setObjectName("Sidebar")
        left.setMinimumWidth(240)
        left.setMaximumWidth(300)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(12, 10, 12, 6)
        filter_lbl = QLabel("JOB SHEETS")
        filter_lbl.setObjectName("SectionLabel")
        filter_row.addWidget(filter_lbl)
        left_lay.addLayout(filter_row)

        self._sheet_list = QListWidget()
        self._sheet_list.setFrameShape(QFrame.Shape.NoFrame)
        self._sheet_list.setSpacing(2)
        self._sheet_list.currentRowChanged.connect(self._on_sheet_selected)
        left_lay.addWidget(self._sheet_list, 1)

        splitter.addWidget(left)

        # Right: detail
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QFrame.Shape.NoFrame)
        self._detail_widget = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_widget)
        self._detail_layout.setContentsMargins(24, 20, 24, 24)
        self._detail_layout.setSpacing(16)
        right.setWidget(self._detail_widget)
        splitter.addWidget(right)

        splitter.setSizes([260, 900])
        root.addWidget(splitter, 1)

        self._show_empty_detail()
        self.refresh_list()

    # ------------------------------------------------------------------ list

    def refresh_list(self):
        self._sheet_list.clear()
        with get_session() as s:
            sheets = (
                s.query(JobSheet)
                .filter(JobSheet.status != JobSheetStatus.archived)
                .order_by(JobSheet.status, JobSheet.updated_at.desc())
                .all()
            )
        for sheet in sheets:
            item = QListWidgetItem()
            widget = SheetListItem(sheet)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, sheet.id)
            self._sheet_list.addItem(item)
            self._sheet_list.setItemWidget(item, widget)

        # Restore selection
        if self._selected_sheet_id:
            for i in range(self._sheet_list.count()):
                it = self._sheet_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == self._selected_sheet_id:
                    self._sheet_list.setCurrentItem(it)
                    break

    def _on_sheet_selected(self, row: int):
        item = self._sheet_list.item(row)
        if item:
            self._selected_sheet_id = item.data(Qt.ItemDataRole.UserRole)
            self._refresh_detail()

    # ------------------------------------------------------------------ detail

    def _clear_detail(self):
        while self._detail_layout.count():
            child = self._detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_empty_detail(self):
        self._clear_detail()
        lbl = QLabel("← Select a job sheet to view details")
        lbl.setStyleSheet("color: #6e7681; font-size: 14px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_layout.addWidget(lbl)
        self._detail_layout.addStretch()

    def _refresh_detail(self):
        if not self._selected_sheet_id:
            return
        with get_session() as s:
            sheet = s.get(JobSheet, self._selected_sheet_id)
            if not sheet:
                self._show_empty_detail()
                return
            items = list(sheet.items)
            active_runs = (
                s.query(JobRun)
                .join(JobItem)
                .filter(
                    JobItem.job_sheet_id == self._selected_sheet_id,
                    JobRun.status == RunStatus.in_progress
                )
                .all()
            )

        self._clear_detail()

        # ── Sheet header ──────────────────────────────────────────────
        top = QHBoxLayout()
        name_col = QVBoxLayout()
        name_col.setSpacing(4)

        name_lbl = QLabel(sheet.name)
        name_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #e6edf3;")
        name_col.addWidget(name_lbl)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge = QLabel(sheet.status.replace("_", " ").title())
        badge.setObjectName(STATUS_BADGE.get(sheet.status, "BadgeBlue"))
        badge.style().unpolish(badge); badge.style().polish(badge)
        badge_row.addWidget(badge)
        if sheet.due_date:
            due = QLabel(f"Due: {sheet.due_date.strftime('%d %b %Y')}")
            due.setStyleSheet("color: #8b949e; font-size: 12px;")
            badge_row.addWidget(due)
        badge_row.addStretch()
        name_col.addLayout(badge_row)
        top.addLayout(name_col, 1)

        # Action buttons
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        btn_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        edit_btn = QPushButton("✎  Edit")
        edit_btn.setFixedHeight(30)
        edit_btn.clicked.connect(self._edit_sheet)
        btn_col.addWidget(edit_btn)

        if sheet.status not in (JobSheetStatus.completed, JobSheetStatus.archived):
            if sheet.progress_pct >= 100:
                complete_btn = QPushButton("✓  Mark Complete")
                complete_btn.setObjectName("PrimaryButton")
                complete_btn.style().unpolish(complete_btn); complete_btn.style().polish(complete_btn)
                complete_btn.clicked.connect(self._mark_sheet_complete)
                btn_col.addWidget(complete_btn)

        archive_btn = QPushButton("Archive")
        archive_btn.setFixedHeight(30)
        archive_btn.setStyleSheet("color: #6e7681;")
        archive_btn.clicked.connect(self._archive_sheet)
        btn_col.addWidget(archive_btn)

        top.addLayout(btn_col)
        self._detail_layout.addLayout(top)

        # ── Progress bar ──────────────────────────────────────────────
        prog_frame = QFrame()
        prog_frame.setObjectName("Card")
        prog_lay = QVBoxLayout(prog_frame)
        prog_lay.setContentsMargins(14, 10, 14, 10)
        prog_lay.setSpacing(6)

        prog_top = QHBoxLayout()
        prog_top.addWidget(QLabel("Overall Progress"))
        pct_lbl = QLabel(f"{sheet.progress_pct:.0f}%")
        pct_lbl.setStyleSheet("color: #3fb950; font-weight: bold;")
        prog_top.addStretch()
        prog_top.addWidget(pct_lbl)
        prog_lay.addLayout(prog_top)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(sheet.progress_pct))
        bar.setFixedHeight(10)
        if sheet.progress_pct >= 100:
            bar.setObjectName("ProgressSuccess")
        prog_lay.addWidget(bar)

        totals = QLabel(
            f"{sheet.total_items} total  ·  "
            f"{sum(i.quantity_in_progress for i in items)} in progress  ·  "
            f"{sheet.completed_items} completed"
        )
        totals.setStyleSheet("color: #6e7681; font-size: 11px;")
        prog_lay.addWidget(totals)
        self._detail_layout.addWidget(prog_frame)

        # Notes
        if sheet.notes:
            notes_lbl = QLabel(sheet.notes)
            notes_lbl.setStyleSheet("color: #8b949e; font-size: 12px; padding: 4px 0;")
            notes_lbl.setWordWrap(True)
            self._detail_layout.addWidget(notes_lbl)

        # ── In-Progress runs ──────────────────────────────────────────
        if active_runs:
            sec = QLabel("IN PROGRESS")
            sec.setObjectName("SectionLabel")
            self._detail_layout.addWidget(sec)
            for run in active_runs:
                row = InProgressRow(run)
                row.action_requested.connect(self._handle_run_action)
                self._detail_layout.addWidget(row)

        # ── Items ─────────────────────────────────────────────────────
        items_header = QHBoxLayout()
        sec2 = QLabel("JOB ITEMS")
        sec2.setObjectName("SectionLabel")
        items_header.addWidget(sec2)
        items_header.addStretch()

        add_btn = QPushButton("+ Add Item")
        add_btn.setObjectName("AccentButton")
        add_btn.setFixedHeight(28)
        add_btn.style().unpolish(add_btn); add_btn.style().polish(add_btn)
        add_btn.clicked.connect(self._add_item)
        items_header.addWidget(add_btn)
        self._detail_layout.addLayout(items_header)

        if items:
            for item in items:
                row = ItemRow(item)
                row.cut_requested.connect(self._handle_cut)
                row.delete_requested.connect(self._handle_delete_item)
                self._detail_layout.addWidget(row)
        else:
            placeholder = QLabel("No items yet — click '+ Add Item' to add products.")
            placeholder.setStyleSheet("color: #6e7681; padding: 12px 0;")
            self._detail_layout.addWidget(placeholder)

        self._detail_layout.addStretch()

    # ------------------------------------------------------------------ actions

    def _new_sheet(self):
        dlg = JobSheetDialog(self)
        if dlg.exec() and dlg.saved_id():
            self._selected_sheet_id = dlg.saved_id()
            self.refresh_list()
            self._refresh_detail()

    def _edit_sheet(self):
        if not self._selected_sheet_id:
            return
        dlg = JobSheetDialog(self, sheet_id=self._selected_sheet_id)
        if dlg.exec():
            self.refresh_list()
            self._refresh_detail()

    def _add_item(self):
        if not self._selected_sheet_id:
            return
        with get_session() as s:
            count = s.query(type('Product', (), {})).count() if False else True
        dlg = AddItemDialog(self._selected_sheet_id, self)
        if dlg.exec():
            self.refresh_list()
            self._refresh_detail()

    def _handle_cut(self, item_id: int):
        dlg = CutDialog(item_id, self)
        dlg.cut_started.connect(lambda _: (self.refresh_list(), self._refresh_detail()))
        dlg.exec()

    def _handle_run_action(self, run_id: int):
        dlg = CompleteRunDialog(run_id, self)
        if dlg.exec():
            self.refresh_list()
            self._refresh_detail()

    def _handle_delete_item(self, item_id: int):
        confirm = QMessageBox.question(
            self, "Remove Item",
            "Remove this item from the job sheet?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            with get_session() as s:
                item = s.get(JobItem, item_id)
                if item:
                    s.delete(item)
                    s.commit()
            self.refresh_list()
            self._refresh_detail()

    def _mark_sheet_complete(self):
        if not self._selected_sheet_id:
            return
        with get_session() as s:
            sheet = s.get(JobSheet, self._selected_sheet_id)
            if sheet:
                sheet.status = JobSheetStatus.completed
                s.commit()
        self.refresh_list()
        self._refresh_detail()

    def _archive_sheet(self):
        if not self._selected_sheet_id:
            return
        confirm = QMessageBox.question(
            self, "Archive Job Sheet",
            "Archive this job sheet? It will be hidden from the active list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            with get_session() as s:
                sheet = s.get(JobSheet, self._selected_sheet_id)
                if sheet:
                    sheet.status = JobSheetStatus.archived
                    s.commit()
            self._selected_sheet_id = None
            self.refresh_list()
            self._show_empty_detail()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_list()
        if self._selected_sheet_id:
            self._refresh_detail()
