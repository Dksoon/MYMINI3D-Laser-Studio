from __future__ import annotations
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGridLayout, QFrame, QScrollArea, QPushButton,
    QProgressBar, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from app.core.database import get_session, JobSheet, JobSheetStatus, Machine, MachineStatus, JobRun, RunStatus


# ─────────────────────────────────────────────
# Helper widgets
# ─────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, title: str, value: str, color_obj: str = "CardValue", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(100)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setObjectName("CardTitle")
        lay.addWidget(self._title_lbl)

        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName(color_obj)
        lay.addWidget(self._value_lbl)

    def set_value(self, v: str):
        self._value_lbl.setText(v)


class MachineCard(QFrame):
    def __init__(self, machine: Machine, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.machine_id = machine.id
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(90)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)

        # Top row: name + status dot
        top = QHBoxLayout()
        top.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        top.addWidget(self._dot)

        name = QLabel(machine.name)
        name.setStyleSheet("font-weight: bold; color: #e6edf3; font-size: 13px;")
        top.addWidget(name)
        top.addStretch()

        self._status_badge = QLabel("Offline")
        self._status_badge.setObjectName("BadgeRed")
        top.addWidget(self._status_badge)

        lay.addLayout(top)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        lay.addWidget(self._progress)

        self._info = QLabel("Not connected")
        self._info.setStyleSheet("color: #6e7681; font-size: 11px;")
        lay.addWidget(self._info)

        self.update_status(machine.status, 0.0)

    def update_status(self, status: str, progress: float = 0.0):
        colors = {
            MachineStatus.offline: ("#6e7681", "Offline", "BadgeRed"),
            MachineStatus.idle:    ("#3fb950", "Idle",    "BadgeGreen"),
            MachineStatus.busy:    ("#d29922", "Busy",    "BadgeYellow"),
            MachineStatus.error:   ("#f85149", "Error",   "BadgeRed"),
        }
        color, label, badge = colors.get(status, ("#6e7681", status, "BadgeRed"))
        self._dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        self._status_badge.setText(label)
        self._status_badge.setObjectName(badge)
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._progress.setValue(int(progress))
        if status == MachineStatus.busy:
            self._info.setText(f"Cutting… {progress:.0f}%")
        elif status == MachineStatus.idle:
            self._info.setText("Ready to cut")
        elif status == MachineStatus.error:
            self._info.setText("Check connection")
        else:
            self._info.setText("Not connected")


class JobRow(QFrame):
    def __init__(self, sheet: JobSheet, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        # Status dot
        dot_color = {
            JobSheetStatus.open:        "#58a6ff",
            JobSheetStatus.in_progress: "#d29922",
            JobSheetStatus.completed:   "#3fb950",
            JobSheetStatus.archived:    "#6e7681",
        }.get(sheet.status, "#6e7681")
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 12px;")
        dot.setFixedWidth(14)
        lay.addWidget(dot)

        # Name
        name = QLabel(sheet.name)
        name.setStyleSheet("color: #e6edf3; font-weight: bold;")
        lay.addWidget(name)

        lay.addStretch()

        # Progress
        pct = sheet.progress_pct
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(pct))
        bar.setFixedSize(100, 6)
        lay.addWidget(bar)

        pct_lbl = QLabel(f"{pct:.0f}%")
        pct_lbl.setStyleSheet("color: #8b949e; font-size: 11px; min-width: 34px;")
        lay.addWidget(pct_lbl)

        items_lbl = QLabel(f"{sheet.completed_items}/{sheet.total_items} pcs")
        items_lbl.setStyleSheet("color: #8b949e; font-size: 11px; min-width: 70px;")
        lay.addWidget(items_lbl)


# ─────────────────────────────────────────────
# Dashboard Page
# ─────────────────────────────────────────────

class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        # Auto-refresh every 8 seconds
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(8000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("HeaderBar")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(24, 16, 24, 12)
        hlay.setSpacing(2)
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        hlay.addWidget(title)
        sub = QLabel("Overview of machines, jobs, and activity")
        sub.setObjectName("PageSubtitle")
        hlay.addWidget(sub)
        root.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(24, 20, 24, 24)
        self._content_layout.setSpacing(20)
        scroll.setWidget(content)
        root.addWidget(scroll)

        self._build_stats()
        self._build_machines()
        self._build_jobs()
        self._content_layout.addStretch()

    def _build_stats(self):
        label = QLabel("OVERVIEW")
        label.setObjectName("SectionLabel")
        self._content_layout.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(12)

        self._stat_machines  = StatCard("Machines Online", "—", "CardAccent")
        self._stat_jobs      = StatCard("Active Job Sheets", "—", "CardWarning")
        self._stat_pending   = StatCard("Items Pending", "—", "CardValue")
        self._stat_completed = StatCard("Completed Today", "—", "CardSuccess")

        grid.addWidget(self._stat_machines,  0, 0)
        grid.addWidget(self._stat_jobs,      0, 1)
        grid.addWidget(self._stat_pending,   0, 2)
        grid.addWidget(self._stat_completed, 0, 3)

        self._content_layout.addLayout(grid)

    def _build_machines(self):
        row = QHBoxLayout()
        row.setSpacing(0)
        label = QLabel("MACHINES")
        label.setObjectName("SectionLabel")
        row.addWidget(label)
        row.addStretch()
        self._content_layout.addLayout(row)

        self._machines_grid = QGridLayout()
        self._machines_grid.setSpacing(12)
        self._content_layout.addLayout(self._machines_grid)
        self._machine_cards: dict[int, MachineCard] = {}

    def _build_jobs(self):
        label = QLabel("ACTIVE JOB SHEETS")
        label.setObjectName("SectionLabel")
        self._content_layout.addWidget(label)

        self._jobs_container = QVBoxLayout()
        self._jobs_container.setSpacing(6)
        self._content_layout.addLayout(self._jobs_container)

    def refresh(self):
        with get_session() as s:
            machines = s.query(Machine).order_by(Machine.id).all()
            active_sheets = (
                s.query(JobSheet)
                .filter(JobSheet.status.in_([JobSheetStatus.open, JobSheetStatus.in_progress]))
                .order_by(JobSheet.updated_at.desc())
                .limit(10)
                .all()
            )
            online = sum(1 for m in machines if m.status != MachineStatus.offline)
            pending = sum(
                (i.quantity_pending for sh in active_sheets for i in sh.items),
                0
            )
            completed_today = (
                s.query(JobRun)
                .filter(
                    JobRun.status == RunStatus.completed,
                    JobRun.completed_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                )
                .count()
            )

        # Update stat cards
        self._stat_machines.set_value(f"{online} / {len(machines)}")
        self._stat_jobs.set_value(str(len(active_sheets)))
        self._stat_pending.set_value(str(pending))
        self._stat_completed.set_value(str(completed_today))

        # Update machine cards
        for m in machines:
            if m.id not in self._machine_cards:
                card = MachineCard(m)
                col = (m.id - 1) % 3
                row = (m.id - 1) // 3
                self._machines_grid.addWidget(card, row, col)
                self._machine_cards[m.id] = card
            else:
                self._machine_cards[m.id].update_status(m.status)

        # Update job rows
        while self._jobs_container.count():
            item = self._jobs_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if active_sheets:
            for sheet in active_sheets:
                self._jobs_container.addWidget(JobRow(sheet))
        else:
            placeholder = QLabel("No active job sheets — go to Job Sheets to create one.")
            placeholder.setStyleSheet("color: #6e7681; padding: 16px 0px;")
            self._jobs_container.addWidget(placeholder)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
