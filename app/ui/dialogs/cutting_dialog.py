"""
Real-time cutting progress dialog.
Handles multi-file products (runs each file in sequence),
updates job tracking, and fires Telegram on completion.
"""
from __future__ import annotations
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QTimer

from app.core.database import (
    get_session, JobRun, JobItem, JobSheet,
    RunStatus, JobSheetStatus
)
from app.core.laser_job   import LaserJob, CutSettings
from app.core.laser_driver import machine_manager
from app.services.telegram_service import telegram_service


class CuttingDialog(QDialog):
    """
    Shown while the laser is cutting.
    Runs all product files in sequence for the given JobRun.

    file_steps: [(file_path, step_label), ...]
    """

    def __init__(
        self,
        run_id:     int,
        machine_id: int,
        file_steps: list[tuple[str, str]],
        settings:   CutSettings,
        cut_type:   str = "full",   # "full" | "parts"
        parent=None,
    ):
        super().__init__(parent)
        self._run_id      = run_id
        self._machine_id  = machine_id
        self._file_steps  = file_steps   # list of (path, label)
        self._settings    = settings
        self._cut_type    = cut_type
        self._step_idx    = 0
        self._active_job: Optional[LaserJob] = None
        self._start_time  = time.time()
        self._aborted     = False
        self._success     = False

        self.setWindowTitle("Cutting in Progress")
        self.setMinimumWidth(500)
        self.setModal(True)
        # Prevent accidental close
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self._build()

        # Elapsed timer
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start(1000)

        # Start first step
        QTimer.singleShot(300, self._run_next_step)

    # ------------------------------------------------------------------ UI

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 20, 24, 20)

        # ── Title ──────────────────────────────────────────────────────
        self._title_lbl = QLabel("Cutting…")
        self._title_lbl.setStyleSheet(
            "font-size:18px; font-weight:bold; color:#e6edf3;"
        )
        lay.addWidget(self._title_lbl)

        # ── Info card ──────────────────────────────────────────────────
        info = QFrame(); info.setObjectName("Card")
        ilay = QVBoxLayout(info)
        ilay.setContentsMargins(14, 12, 14, 12)
        ilay.setSpacing(6)

        self._step_lbl = QLabel("Preparing…")
        self._step_lbl.setStyleSheet("color:#d29922; font-weight:bold;")
        ilay.addWidget(self._step_lbl)

        with get_session() as s:
            run  = s.get(JobRun, self._run_id)
            mname = run.machine.name if run and run.machine else "—"
            pname = run.job_item.product.name if run and run.job_item and run.job_item.product else "—"
            qty   = run.quantity if run else 1

        for label, value in [
            ("Product:", pname),
            ("Quantity:", f"{qty} unit(s)"),
            ("Machine:",  mname),
        ]:
            row = QHBoxLayout()
            l = QLabel(label); l.setStyleSheet("color:#6e7681;"); l.setFixedWidth(72)
            v = QLabel(value); v.setStyleSheet("color:#e6edf3;")
            row.addWidget(l); row.addWidget(v); row.addStretch()
            ilay.addLayout(row)

        lay.addWidget(info)

        # ── Step progress ──────────────────────────────────────────────
        step_frame = QFrame(); step_frame.setObjectName("Card")
        step_lay   = QVBoxLayout(step_frame)
        step_lay.setContentsMargins(14, 12, 14, 12)
        step_lay.setSpacing(8)

        self._file_lbl = QLabel("—")
        self._file_lbl.setStyleSheet("color:#58a6ff; font-size:13px; font-weight:bold;")
        step_lay.addWidget(self._file_lbl)

        # Per-step progress
        self._step_bar = QProgressBar()
        self._step_bar.setRange(0, 100)
        self._step_bar.setValue(0)
        self._step_bar.setFixedHeight(10)
        step_lay.addWidget(self._step_bar)

        pct_row = QHBoxLayout()
        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setStyleSheet("color:#d29922; font-weight:bold;")
        pct_row.addWidget(self._pct_lbl)
        pct_row.addStretch()
        self._elapsed_lbl = QLabel("0:00")
        self._elapsed_lbl.setStyleSheet("color:#6e7681; font-size:12px;")
        pct_row.addWidget(self._elapsed_lbl)
        step_lay.addLayout(pct_row)

        self._msg_lbl = QLabel("Initialising…")
        self._msg_lbl.setStyleSheet("color:#6e7681; font-size:12px;")
        step_lay.addWidget(self._msg_lbl)

        lay.addWidget(step_frame)

        # ── Step indicators ────────────────────────────────────────────
        if len(self._file_steps) > 1:
            dots_row = QHBoxLayout()
            dots_row.setSpacing(8)
            dots_row.addStretch()
            self._step_dots: list[QLabel] = []
            prefix = "Sheet" if self._cut_type == "full" else "Part"
            for i, (_, label) in enumerate(self._file_steps):
                dot = QLabel(f"  {prefix} {i+1}: {label}  ")
                dot.setObjectName("BadgeRed")
                dot.style().unpolish(dot); dot.style().polish(dot)
                self._step_dots.append(dot)
                dots_row.addWidget(dot)
            dots_row.addStretch()
            lay.addLayout(dots_row)

        # ── Buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._abort_btn = QPushButton("✕  Abort")
        self._abort_btn.setObjectName("DangerButton")
        self._abort_btn.style().unpolish(self._abort_btn)
        self._abort_btn.style().polish(self._abort_btn)
        self._abort_btn.setFixedHeight(36)
        self._abort_btn.clicked.connect(self._abort)
        btn_row.addWidget(self._abort_btn)

        btn_row.addStretch()

        self._next_btn = QPushButton("Next Step  →")
        self._next_btn.setObjectName("AccentButton")
        self._next_btn.style().unpolish(self._next_btn)
        self._next_btn.style().polish(self._next_btn)
        self._next_btn.setFixedHeight(36)
        self._next_btn.setVisible(False)
        self._next_btn.clicked.connect(self._run_next_step)
        btn_row.addWidget(self._next_btn)

        self._done_btn = QPushButton("✓  Done — Close")
        self._done_btn.setObjectName("PrimaryButton")
        self._done_btn.style().unpolish(self._done_btn)
        self._done_btn.style().polish(self._done_btn)
        self._done_btn.setFixedHeight(36)
        self._done_btn.setVisible(False)
        self._done_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._done_btn)

        lay.addLayout(btn_row)

    # ------------------------------------------------------------------ step runner

    def _run_next_step(self):
        if self._aborted:
            return
        if self._step_idx >= len(self._file_steps):
            self._all_steps_done()
            return

        self._next_btn.setVisible(False)
        file_path, label = self._file_steps[self._step_idx]
        total = len(self._file_steps)

        # Update step dots
        if hasattr(self, "_step_dots"):
            for i, dot in enumerate(self._step_dots):
                if i < self._step_idx:
                    dot.setObjectName("BadgeGreen")
                elif i == self._step_idx:
                    dot.setObjectName("BadgeYellow")
                else:
                    dot.setObjectName("BadgeRed")
                dot.style().unpolish(dot); dot.style().polish(dot)

        # Labels — "Sheet X of Y" for full cuts, "Part X of Y" for parts
        n = self._step_idx + 1
        if self._cut_type == "full":
            step_text = f"Sheet {n} of {total}:  {label}"
        else:
            step_text = f"Part {n} of {total}:  {label}"
        self._step_lbl.setText(step_text)
        from pathlib import Path
        self._file_lbl.setText(f"File:  {Path(file_path).name}")
        self._step_bar.setValue(0)
        self._pct_lbl.setText("0%")
        self._msg_lbl.setText("Starting…")

        def _progress(pct: float, msg: str):
            self._step_bar.setValue(int(pct))
            self._pct_lbl.setText(f"{pct:.0f}%")
            self._msg_lbl.setText(msg[:60])

        def _done(ok: bool, msg: str):
            if ok:
                self._step_bar.setValue(100)
                self._pct_lbl.setText("100%")
                self._step_idx += 1
                if self._step_idx < len(self._file_steps):
                    # More steps — prompt depends on cut type
                    next_label = self._file_steps[self._step_idx][1]
                    if self._cut_type == "full":
                        prompt = (
                            f"Sheet {self._step_idx} done.  "
                            f"Load sheet {self._step_idx + 1} of material into machine, "
                            f"then click Next."
                        )
                    else:
                        prompt = (
                            f"Part done.  "
                            f"Ready to cut next part: {next_label}.  Click Next."
                        )
                    self._msg_lbl.setText(prompt)
                    self._msg_lbl.setStyleSheet("color:#3fb950; font-size:12px;")
                    self._next_btn.setText(f"Next →  {next_label}")
                    self._next_btn.setVisible(True)
                    if hasattr(self, "_step_dots") and self._step_idx - 1 < len(self._step_dots):
                        dot = self._step_dots[self._step_idx - 1]
                        dot.setObjectName("BadgeGreen")
                        dot.style().unpolish(dot); dot.style().polish(dot)
                else:
                    self._all_steps_done()
            else:
                if not self._aborted:
                    self._msg_lbl.setText(f"Error: {msg}")
                    self._msg_lbl.setStyleSheet("color:#f85149; font-size:12px;")
                    self._finish_run(success=False, message=msg)

        job = LaserJob(
            machine_id  = self._machine_id,
            file_path   = file_path,
            settings    = self._settings,
            trace_only  = False,
            on_progress = _progress,
            on_done     = _done,
        )
        self._active_job = job
        job.start()

    def _all_steps_done(self):
        # Update step dots
        if hasattr(self, "_step_dots"):
            for dot in self._step_dots:
                dot.setObjectName("BadgeGreen")
                dot.style().unpolish(dot); dot.style().polish(dot)

        self._title_lbl.setText("✓  Cut Complete")
        self._title_lbl.setStyleSheet(
            "font-size:18px; font-weight:bold; color:#3fb950;"
        )
        self._step_lbl.setText("All steps finished successfully")
        self._step_lbl.setStyleSheet("color:#3fb950; font-weight:bold;")
        self._step_bar.setValue(100)
        self._pct_lbl.setText("100%")
        self._msg_lbl.setText("Job complete!")
        self._msg_lbl.setStyleSheet("color:#3fb950; font-size:12px;")
        self._abort_btn.setVisible(False)
        self._done_btn.setVisible(True)
        self._finish_run(success=True, message="Completed")

    # ------------------------------------------------------------------ abort

    def _abort(self):
        self._aborted = True
        if self._active_job:
            self._active_job.abort()
        self._title_lbl.setText("✕  Aborted")
        self._title_lbl.setStyleSheet(
            "font-size:18px; font-weight:bold; color:#f85149;"
        )
        self._step_lbl.setText("Job was cancelled")
        self._step_lbl.setStyleSheet("color:#f85149;")
        self._abort_btn.setVisible(False)
        self._next_btn.setVisible(False)
        self._done_btn.setText("Close")
        self._done_btn.setVisible(True)
        self._finish_run(success=False, message="Cancelled by user")

    # ------------------------------------------------------------------ DB + Telegram

    def _finish_run(self, success: bool, message: str):
        self._elapsed_timer.stop()
        self._success = success

        with get_session() as s:
            run  = s.get(JobRun, self._run_id)
            if not run:
                return
            item  = run.job_item
            sheet = item.job_sheet if item else None

            run.completed_at = datetime.utcnow()
            run.notes        = message

            if success:
                run.status = RunStatus.completed
                if item:
                    item.quantity_in_progress = max(0, item.quantity_in_progress - run.quantity)
                    item.quantity_completed  += run.quantity
            else:
                run.status = RunStatus.cancelled
                if item:
                    item.quantity_in_progress = max(0, item.quantity_in_progress - run.quantity)

            # Check if whole sheet is done
            sheet_done = False
            if sheet and success and all(i.is_done for i in sheet.items):
                sheet.status = JobSheetStatus.completed
                sheet_done   = True

            s.commit()

            sheet_name   = sheet.name          if sheet else "—"
            product_name = item.product.name   if item and item.product else "—"
            machine_name = run.machine.name    if run.machine else "—"
            qty          = run.quantity

        # Telegram
        if success:
            telegram_service.notify_job_completed(
                sheet_name, product_name, qty, machine_name
            )
            if sheet_done:
                telegram_service.notify_job_sheet_done(sheet_name)
        else:
            telegram_service.notify_job_failed(
                sheet_name, product_name, message
            )

    # ------------------------------------------------------------------ timer

    def _tick_elapsed(self):
        elapsed = int(time.time() - self._start_time)
        m, s    = divmod(elapsed, 60)
        self._elapsed_lbl.setText(f"{m}:{s:02d}")

    def closeEvent(self, event):
        # Only allow close if done or aborted
        if self._active_job and not self._aborted and not self._success:
            event.ignore()
        else:
            self._elapsed_timer.stop()
            super().closeEvent(event)

    @property
    def succeeded(self) -> bool:
        return self._success
