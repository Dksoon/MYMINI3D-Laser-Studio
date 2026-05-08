"""Create / Edit a Job Sheet."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QDateEdit, QPushButton,
    QDialogButtonBox, QFrame
)
from PyQt6.QtCore import Qt, QDate

from app.core.database import get_session, JobSheet, JobSheetStatus


class JobSheetDialog(QDialog):
    """Create a new job sheet or edit an existing one."""

    def __init__(self, parent=None, sheet_id: Optional[int] = None):
        super().__init__(parent)
        self._sheet_id = sheet_id
        self._sheet: Optional[JobSheet] = None
        self.setWindowTitle("Edit Job Sheet" if sheet_id else "New Job Sheet")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build()
        if sheet_id:
            self._load()

    # ------------------------------------------------------------------ UI

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel("Edit Job Sheet" if self._sheet_id else "New Job Sheet")
        title.setObjectName("PageTitle")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e6edf3;")
        lay.addWidget(title)

        # Form
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Order #042 — Client ABC")
        form.addRow("Job Name *", self._name_edit)

        self._due_edit = QDateEdit()
        self._due_edit.setDisplayFormat("dd/MM/yyyy")
        self._due_edit.setDate(QDate.currentDate())
        self._due_edit.setCalendarPopup(True)
        self._due_edit.setSpecialValueText("No due date")
        form.addRow("Due Date", self._due_edit)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Optional notes, customer reference, etc.")
        self._notes_edit.setFixedHeight(80)
        form.addRow("Notes", self._notes_edit)

        lay.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Save Job Sheet")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.style().unpolish(ok_btn)
        ok_btn.style().polish(ok_btn)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------ data

    def _load(self):
        with get_session() as s:
            sheet = s.get(JobSheet, self._sheet_id)
            if not sheet:
                return
            self._name_edit.setText(sheet.name)
            self._notes_edit.setPlainText(sheet.notes or "")
            if sheet.due_date:
                qd = QDate(sheet.due_date.year, sheet.due_date.month, sheet.due_date.day)
                self._due_edit.setDate(qd)

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            self._name_edit.setStyleSheet("border: 1px solid #f85149;")
            return

        qd = self._due_edit.date()
        due = datetime(qd.year(), qd.month(), qd.day()) if qd.isValid() else None

        with get_session() as s:
            if self._sheet_id:
                sheet = s.get(JobSheet, self._sheet_id)
                if sheet:
                    sheet.name = name
                    sheet.notes = self._notes_edit.toPlainText().strip()
                    sheet.due_date = due
                    sheet.updated_at = datetime.utcnow()
            else:
                sheet = JobSheet(
                    name=name,
                    notes=self._notes_edit.toPlainText().strip(),
                    due_date=due,
                    status=JobSheetStatus.open,
                )
                s.add(sheet)
            s.commit()
            self._sheet_id = sheet.id

        self.accept()

    def saved_id(self) -> Optional[int]:
        return self._sheet_id
