"""
Import Backup Dialog — restores %APPDATA%/MYMINI3D/ from a .zip backup file.
WARNS before overwriting. Validates the zip is a valid MYMINI3D backup.
After import, prompts user to restart the app.
"""
from __future__ import annotations
import zipfile
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QProgressBar, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from app.core.config import get_app_data_dir


# ── Background worker ─────────────────────────────────────────────────

class _ImportWorker(QThread):
    progress = pyqtSignal(int, str)   # percent, current file name
    finished = pyqtSignal(bool, str)  # ok, message

    def __init__(self, zip_path: str):
        super().__init__()
        self._zip = zip_path

    def run(self):
        try:
            app_dir = get_app_data_dir()
            with zipfile.ZipFile(self._zip, "r") as zf:
                names = zf.namelist()
                total = max(1, len(names))
                for i, name in enumerate(names):
                    zf.extract(name, app_dir)
                    pct = int((i + 1) / total * 100)
                    self.progress.emit(pct, Path(name).name)
            self.finished.emit(True, f"Restored {total} files. Please restart the app.")
        except Exception as e:
            self.finished.emit(False, str(e))


# ── Dialog ────────────────────────────────────────────────────────────

class ImportBackupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Backup")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._worker = None
        self._zip_valid = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 18, 20, 18)

        title = QLabel("Import Backup")
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#e6edf3;")
        lay.addWidget(title)

        # Warning box
        warn = QFrame()
        warn.setStyleSheet(
            "background:#3a1200; border:1px solid #b62324; border-radius:4px;"
        )
        wlay = QVBoxLayout(warn)
        wlay.setContentsMargins(14, 10, 14, 10)
        wlay.setSpacing(4)
        w1 = QLabel("⚠  WARNING")
        w1.setStyleSheet("color:#f85149; font-weight:bold; font-size:12px; border:none;")
        wlay.addWidget(w1)
        w2 = QLabel(
            "Importing a backup will OVERWRITE all current data:\n"
            "products, job history, settings, and library files.\n"
            "This cannot be undone. Export a backup first if needed."
        )
        w2.setStyleSheet("color:#e6edf3; font-size:11px; border:none;")
        w2.setWordWrap(True)
        wlay.addWidget(w2)
        lay.addWidget(warn)

        # Backup file selection
        src_frame = QFrame()
        src_frame.setObjectName("Card")
        slay = QVBoxLayout(src_frame)
        slay.setContentsMargins(14, 10, 14, 10)
        slay.setSpacing(8)
        slay.addWidget(QLabel("BACKUP FILE:").also(lambda l: l.setObjectName("SectionLabel")))

        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self._src_edit = QLineEdit()
        self._src_edit.setPlaceholderText("Browse to .zip backup file…")
        self._src_edit.setStyleSheet("font-size:11px;")
        self._src_edit.textChanged.connect(self._validate_zip)
        src_row.addWidget(self._src_edit, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(72)
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse)
        src_row.addWidget(browse_btn)
        slay.addLayout(src_row)

        # Validation info
        self._validate_lbl = QLabel("")
        self._validate_lbl.setStyleSheet("color:#6e7681; font-size:11px;")
        slay.addWidget(self._validate_lbl)
        lay.addWidget(src_frame)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(8)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#6e7681; font-size:11px;")
        self._status_lbl.setWordWrap(True)
        lay.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()

        self._import_btn = QPushButton("Import & Overwrite")
        self._import_btn.setFixedHeight(32)
        self._import_btn.setEnabled(False)
        self._import_btn.setStyleSheet(
            "background:#b62324; color:#fff; border:none; border-radius:4px;"
            "font-size:13px; font-weight:bold; min-height:0; max-height:32px;"
        )
        self._import_btn.clicked.connect(self._confirm_import)
        btn_row.addWidget(self._import_btn)
        lay.addLayout(btn_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Backup File",
            str(Path.home() / "Desktop"),
            "Zip Archive (*.zip)"
        )
        if path:
            self._src_edit.setText(path)

    def _validate_zip(self, path: str):
        path = path.strip()
        self._zip_valid = False
        self._import_btn.setEnabled(False)

        if not path:
            self._validate_lbl.setText("")
            return

        p = Path(path)
        if not p.exists():
            self._validate_lbl.setText("✕  File not found.")
            self._validate_lbl.setStyleSheet("color:#f85149; font-size:11px;")
            return

        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                has_db = any("mymini3d.db" in n for n in names)
                file_count = len(names)
                lib_count  = sum(1 for n in names if n.startswith("library/"))

            if not has_db:
                self._validate_lbl.setText(
                    "⚠  This zip doesn't look like a MYMINI3D backup (no database found).\n"
                    "You can still import it, but unexpected results may occur."
                )
                self._validate_lbl.setStyleSheet("color:#d29922; font-size:11px;")
            else:
                self._validate_lbl.setText(
                    f"✓  Valid backup — {file_count} files total, "
                    f"{lib_count} library files."
                )
                self._validate_lbl.setStyleSheet("color:#3fb950; font-size:11px;")

            self._zip_valid = True
            self._import_btn.setEnabled(True)
        except zipfile.BadZipFile:
            self._validate_lbl.setText("✕  Not a valid zip file.")
            self._validate_lbl.setStyleSheet("color:#f85149; font-size:11px;")

    def _confirm_import(self):
        reply = QMessageBox.warning(
            self, "Confirm Import",
            "This will OVERWRITE all your current data.\n\n"
            "Are you absolutely sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._start_import()

    def _start_import(self):
        zip_path = self._src_edit.text().strip()
        self._import_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_lbl.setText("Importing…")
        self._status_lbl.setStyleSheet("color:#6e7681; font-size:11px;")

        self._worker = _ImportWorker(zip_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, pct: int, fname: str):
        self._progress.setValue(pct)
        self._status_lbl.setText(f"Restoring: {fname}")

    def _on_finished(self, ok: bool, msg: str):
        self._progress.setValue(100 if ok else 0)
        if ok:
            self._status_lbl.setText(f"✓  {msg}")
            self._status_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
            QMessageBox.information(
                self, "Import Complete",
                "Backup restored successfully.\n\n"
                "Please close and reopen the app for all changes to take effect."
            )
            self.accept()
        else:
            self._import_btn.setEnabled(True)
            self._status_lbl.setText(f"✕  Import failed: {msg}")
            self._status_lbl.setStyleSheet("color:#f85149; font-size:11px;")


# Patch .also()
from PyQt6.QtWidgets import QWidget as _QW
if not hasattr(_QW, "also"):
    def _also(self, fn): fn(self); return self
    _QW.also = _also
