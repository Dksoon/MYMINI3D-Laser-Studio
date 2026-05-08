"""Smart Cut Dialog — the core workflow trigger."""
from __future__ import annotations
import json
import os
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QComboBox, QPushButton,
    QDialogButtonBox, QFrame, QListWidget, QListWidgetItem,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.core.database import (
    get_session, JobItem, JobRun, JobSheet, Product, ProductFile,
    Machine, MachineStatus, RunStatus, JobSheetStatus
)
from app.services.telegram_service import telegram_service


class CutDialog(QDialog):
    """
    Opened when the user clicks ✂ on a pending job item.
    Handles smart quantity calculation, machine selection,
    and moves items to In Progress.
    """
    cut_started = pyqtSignal(int)   # emits job_run_id

    def __init__(self, job_item_id: int, parent=None):
        super().__init__(parent)
        self._job_item_id = job_item_id
        self._item: Optional[JobItem] = None
        self._product: Optional[Product] = None
        self._machines: list[Machine] = []
        self._cut_type = "full"   # set properly in _load_data
        self.setWindowTitle("Start Cut")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._load_data()
        self._build()

    # ------------------------------------------------------------------ data

    def _load_data(self):
        with get_session() as s:
            self._item = s.get(JobItem, self._job_item_id)
            if self._item:
                self._product = self._item.product
                all_files = list(self._product.files) if self._product else []
                cut_type = self._item.cut_type or "full"

                if cut_type == "full" and self._item.main_file_id:
                    mf = s.get(ProductFile, self._item.main_file_id)
                    if mf:
                        self._files = [mf]
                    else:
                        # Fallback to all main files
                        self._files = [f for f in all_files if f.file_role == "main"] or all_files
                elif cut_type == "parts":
                    try:
                        part_ids = json.loads(self._item.part_file_ids or "[]")
                    except Exception:
                        part_ids = []
                    if part_ids:
                        fmap = {f.id: f for f in all_files}
                        self._files = [fmap[pid] for pid in part_ids if pid in fmap]
                    else:
                        self._files = [f for f in all_files if f.file_role == "part"] or all_files
                else:
                    self._files = all_files

                self._cut_type = cut_type
            self._machines = s.query(Machine).order_by(Machine.id).all()

    # ------------------------------------------------------------------ UI

    def _build(self):
        if not self._item or not self._product:
            self.reject()
            return

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel("Start Cut Job")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e6edf3;")
        lay.addWidget(title)

        # Product name + cut type badge
        prod_row = QHBoxLayout()
        prod_row.setSpacing(10)
        prod_lbl = QLabel(self._product.name)
        prod_lbl.setStyleSheet("color:#8b949e; font-size:13px;")
        prod_row.addWidget(prod_lbl)

        if self._cut_type == "full":
            ct_badge = QLabel("★ Full Sheet")
            ct_badge.setStyleSheet(
                "color:#3fb950; background:#1a2d1a; border:1px solid #2ea043;"
                "border-radius:3px; padding:2px 8px; font-size:11px;"
            )
        else:
            ct_badge = QLabel("⚙ Individual Parts")
            ct_badge.setStyleSheet(
                "color:#58a6ff; background:#0d1f38; border:1px solid #1f6feb;"
                "border-radius:3px; padding:2px 8px; font-size:11px;"
            )
        prod_row.addWidget(ct_badge)
        prod_row.addStretch()
        lay.addLayout(prod_row)

        # Divider
        div = QFrame(); div.setObjectName("SidebarDivider")
        lay.addWidget(div)

        # Files to cut — label varies by cut type
        if self._cut_type == "full":
            files_header = "SHEET FILE TO CUT:"
        else:
            files_header = "PARTS TO CUT (in order):"
        files_label = QLabel(files_header)
        files_label.setObjectName("SectionLabel")
        lay.addWidget(files_label)

        self._files_list = QListWidget()
        self._files_list.setMaximumHeight(120)
        self._files_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        if self._files:
            for n, f in enumerate(self._files, 1):
                fname = os.path.basename(f.file_path) if f.file_path else "(no file)"
                exists = Path(f.file_path).exists() if f.file_path else False
                if self._cut_type == "full":
                    lbl = f"Sheet {f.sheet_number or n}: {fname}"
                else:
                    lbl = f"{f.part_name or fname}"
                    if n > 1 or len(self._files) > 1:
                        lbl = f"{n}. {lbl}"
                status = "" if exists else "  ⚠ file missing"
                item = QListWidgetItem(f"  {lbl}{status}")
                item.setData(Qt.ItemDataRole.UserRole, f.file_path)
                if not exists:
                    item.setForeground(Qt.GlobalColor.darkRed)
                self._files_list.addItem(item)
        else:
            self._files_list.addItem("  (No files assigned — add files in Library)")

        lay.addWidget(self._files_list)

        # Form
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        pending = self._item.quantity_pending
        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, max(1, pending))
        self._qty_spin.setValue(pending)
        self._qty_spin.setSuffix("  units")
        self._qty_spin.valueChanged.connect(self._update_calc)
        form.addRow(f"Quantity to cut  (max {pending})", self._qty_spin)

        self._machine_combo = QComboBox()
        for m in self._machines:
            status_str = f"  [{m.status.upper()}]" if m.status != MachineStatus.offline else "  [Offline]"
            self._machine_combo.addItem(f"{m.name}{status_str}", userData=m.id)
        form.addRow("Machine", self._machine_combo)

        lay.addLayout(form)

        # Smart calculation card
        calc_frame = QFrame()
        calc_frame.setObjectName("Card")
        calc_lay = QVBoxLayout(calc_frame)
        calc_lay.setContentsMargins(14, 12, 14, 12)
        calc_lay.setSpacing(6)

        sheets_row = QHBoxLayout()
        sheets_icon = QLabel("◈")
        sheets_icon.setStyleSheet("color: #d29922; font-size: 16px;")
        sheets_row.addWidget(sheets_icon)
        self._sheets_lbl = QLabel()
        self._sheets_lbl.setStyleSheet("color: #d29922; font-weight: bold;")
        sheets_row.addWidget(self._sheets_lbl)
        sheets_row.addStretch()
        calc_lay.addLayout(sheets_row)

        self._units_per_lbl = QLabel()
        self._units_per_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        calc_lay.addWidget(self._units_per_lbl)

        files_row = QHBoxLayout()
        files_icon = QLabel("⎙")
        files_icon.setStyleSheet("color: #58a6ff; font-size: 14px;")
        files_row.addWidget(files_icon)
        self._files_count_lbl = QLabel()
        self._files_count_lbl.setStyleSheet("color: #58a6ff;")
        files_row.addWidget(self._files_count_lbl)
        files_row.addStretch()
        calc_lay.addLayout(files_row)

        self._action_note = QLabel()
        self._action_note.setStyleSheet("color: #6e7681; font-size: 11px;")
        calc_lay.addWidget(self._action_note)

        lay.addWidget(calc_frame)
        self._update_calc()

        # Warning if machine offline
        self._warn_lbl = QLabel()
        self._warn_lbl.setStyleSheet("color: #f85149; font-size: 12px;")
        self._warn_lbl.setWordWrap(True)
        lay.addWidget(self._warn_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()

        open_btn = QPushButton("Open Files Only")
        open_btn.setToolTip("Open SVG files without tracking — for preview/manual use")
        open_btn.clicked.connect(self._open_files_only)
        btn_row.addWidget(open_btn)

        self._cut_btn = QPushButton("✂  Start Cut")
        self._cut_btn.setObjectName("CutButton")
        self._cut_btn.style().unpolish(self._cut_btn)
        self._cut_btn.style().polish(self._cut_btn)
        self._cut_btn.clicked.connect(self._start_cut)
        btn_row.addWidget(self._cut_btn)

        lay.addLayout(btn_row)

    # ------------------------------------------------------------------ logic

    def _update_calc(self):
        qty = self._qty_spin.value()
        ups = self._product.units_per_sheet if self._product else 1
        file_count = len(self._files)
        cut_type = getattr(self, "_cut_type", "full")

        if cut_type == "full":
            sheets = math.ceil(qty / max(1, ups))
            self._sheets_lbl.setText(
                f"Load {sheets} material sheet{'s' if sheets != 1 else ''}"
            )
            self._units_per_lbl.setText(
                f"   {ups} unit{'s' if ups != 1 else ''} per sheet  →  "
                f"cutting {qty} unit{'s' if qty != 1 else ''}"
            )
            self._files_count_lbl.setText("1 sheet file per run")
        else:
            self._sheets_lbl.setText(
                f"Cutting {file_count} part{'s' if file_count != 1 else ''} per unit"
            )
            self._units_per_lbl.setText(
                f"   {qty} unit{'s' if qty != 1 else ''} × "
                f"{file_count} part{'s' if file_count != 1 else ''} = "
                f"{qty * file_count} cuts total"
            )
            self._files_count_lbl.setText(
                f"{file_count} part file{'s' if file_count != 1 else ''} will run in sequence"
            )

        self._action_note.setText(
            f"Clicking 'Start Cut' will move {qty} unit{'s' if qty != 1 else ''} "
            f"to In Progress and notify Telegram."
        )

    def _open_files_only(self):
        for f in self._files:
            if f.file_path and os.path.exists(f.file_path):
                os.startfile(f.file_path)

    def _start_cut(self):
        qty = self._qty_spin.value()
        machine_id = self._machine_combo.currentData()

        with get_session() as s:
            item = s.get(JobItem, self._job_item_id)
            if not item or item.quantity_pending < qty:
                QMessageBox.warning(self, "Error", "Not enough pending quantity.")
                return

            machine = s.get(Machine, machine_id) if machine_id else None
            machine_name = machine.name if machine else "Unknown"

            # Create one run per file (or one combined run if single-file)
            run = JobRun(
                job_item_id=self._job_item_id,
                machine_id=machine_id,
                quantity=qty,
                file_index=0,
                status=RunStatus.in_progress,
                started_at=datetime.utcnow(),
            )
            s.add(run)

            # Deduct from pending → in_progress
            item.quantity_in_progress += qty

            # Update job sheet status
            sheet = s.get(JobSheet, item.job_sheet_id)
            if sheet and sheet.status == JobSheetStatus.open:
                sheet.status = JobSheetStatus.in_progress

            s.commit()
            run_id = run.id

            # Notify Telegram
            sheet_name = sheet.name if sheet else "Unknown"
            product_name = item.product.name if item.product else "Unknown"

        telegram_service.notify_job_started(sheet_name, product_name, qty, machine_name)

        # ── Build file_steps for CuttingDialog ─────────────────────
        cut_type = getattr(self, "_cut_type", "full")
        file_steps = []
        total = len(self._files)
        for n, f in enumerate(self._files, 1):
            if not (f.file_path and Path(f.file_path).exists()):
                continue
            if cut_type == "full":
                label = f"Sheet {f.sheet_number or n}"
            else:
                label = f.part_name or Path(f.file_path).name
            file_steps.append((f.file_path, label))

        if not file_steps:
            # No files attached — warn but still track in job sheet
            QMessageBox.warning(
                self, "No Files",
                "No SVG/DXF files are attached to this product.\n\n"
                "Add files in the Library first.\n\n"
                "The job has been moved to In Progress — "
                "mark it Done manually when finished."
            )
            self.cut_started.emit(run_id)
            self.accept()
            return

        # ── Check machine is connected ──────────────────────────────
        from app.core.laser_driver import machine_manager
        drv = machine_manager.status(machine_id)
        if not drv.connected:
            reply = QMessageBox.question(
                self, "Machine Not Connected",
                f"'{machine_name}' is not connected.\n\n"
                "Go to Machines → Connect first.\n\n"
                "Start job anyway (manual mode — no laser firing)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                # Roll back DB changes
                with get_session() as s:
                    run = s.get(JobRun, run_id)
                    item = s.get(JobItem, self._job_item_id)
                    if run:  s.delete(run)
                    if item: item.quantity_in_progress = max(0, item.quantity_in_progress - qty)
                    s.commit()
                return
            # Manual mode — open files with default viewer
            for path, _ in file_steps:
                os.startfile(path)
            self.cut_started.emit(run_id)
            self.accept()
            return

        # ── Open CuttingDialog — laser fires ────────────────────────
        from app.core.laser_job import CutSettings
        from app.ui.dialogs.cutting_dialog import CuttingDialog
        from app.core.config import load_config
        cfg      = load_config()
        settings = CutSettings(
            speed_cut_mm_s    = cfg.get("default_speed_cut",    8.0),
            speed_vector_mm_s = cfg.get("default_speed_vector", 20.0),
            speed_raster_mm_s = cfg.get("default_speed_raster", 200.0),
            passes            = 1,
        )

        self.accept()   # close CutDialog before opening CuttingDialog

        cutting_dlg = CuttingDialog(
            run_id     = run_id,
            machine_id = machine_id,
            file_steps = file_steps,
            settings   = settings,
            cut_type   = cut_type,
            parent     = self.parent(),
        )
        cutting_dlg.exec()
        self.cut_started.emit(run_id)


class CompleteRunDialog(QDialog):
    """Mark an In Progress run as done or cancelled."""

    def __init__(self, run_id: int, parent=None):
        super().__init__(parent)
        self._run_id = run_id
        self.setWindowTitle("Complete / Cancel Run")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._build()

    def _build(self):
        with get_session() as s:
            run = s.get(JobRun, self._run_id)
            if not run:
                self.reject(); return
            item = run.job_item
            product_name = item.product.name if item and item.product else "Unknown"
            machine = run.machine
            machine_name = machine.name if machine else "—"
            qty = run.quantity

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 20, 24, 20)

        title = QLabel("Complete or Cancel Run")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e6edf3;")
        lay.addWidget(title)

        info = QFrame(); info.setObjectName("Card")
        ilay = QVBoxLayout(info)
        ilay.setContentsMargins(14, 12, 14, 12)
        ilay.setSpacing(4)
        ilay.addWidget(QLabel(f"Product:   {product_name}"))
        ilay.addWidget(QLabel(f"Quantity:  {qty} unit(s)"))
        ilay.addWidget(QLabel(f"Machine:   {machine_name}"))
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        cancel_run_btn = QPushButton("✕  Cancel Run")
        cancel_run_btn.setObjectName("DangerButton")
        cancel_run_btn.style().unpolish(cancel_run_btn)
        cancel_run_btn.style().polish(cancel_run_btn)
        cancel_run_btn.clicked.connect(self._cancel_run)
        btn_row.addWidget(cancel_run_btn)

        btn_row.addStretch()

        done_btn = QPushButton("✓  Mark as Done")
        done_btn.setObjectName("PrimaryButton")
        done_btn.style().unpolish(done_btn)
        done_btn.style().polish(done_btn)
        done_btn.clicked.connect(self._complete_run)
        btn_row.addWidget(done_btn)

        lay.addLayout(btn_row)

    def _complete_run(self):
        with get_session() as s:
            run = s.get(JobRun, self._run_id)
            if not run: return
            item = run.job_item
            sheet = item.job_sheet if item else None

            run.status = RunStatus.completed
            run.completed_at = datetime.utcnow()
            if item:
                item.quantity_in_progress = max(0, item.quantity_in_progress - run.quantity)
                item.quantity_completed  += run.quantity

            # Check if sheet is fully done
            if sheet and all(i.is_done for i in sheet.items):
                sheet.status = JobSheetStatus.completed
                s.commit()
                telegram_service.notify_job_sheet_done(sheet.name)
            else:
                s.commit()

            if item and item.product and sheet:
                telegram_service.notify_job_completed(
                    sheet.name, item.product.name, run.quantity,
                    run.machine.name if run.machine else "—"
                )
        self.accept()

    def _cancel_run(self):
        with get_session() as s:
            run = s.get(JobRun, self._run_id)
            if not run: return
            item = run.job_item
            run.status = RunStatus.cancelled
            run.completed_at = datetime.utcnow()
            if item:
                item.quantity_in_progress = max(0, item.quantity_in_progress - run.quantity)
            s.commit()
        self.accept()
