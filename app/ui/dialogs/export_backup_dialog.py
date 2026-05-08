"""
Export Backup Dialog — packages %APPDATA%/MYMINI3D/ into a dated .zip file.
Includes: database, library files, config.json, thumbnails.
"""
from __future__ import annotations
import zipfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QProgressBar, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from app.core.config import get_app_data_dir


# ── Background worker ─────────────────────────────────────────────────

class _ExportWorker(QThread):
    progress = pyqtSignal(int, str)   # percent, current file name
    finished = pyqtSignal(bool, str)  # ok, message

    def __init__(self, dest_path: str):
        super().__init__()
        self._dest = dest_path

    def run(self):
        try:
            app_dir = get_app_data_dir()
            all_files = [f for f in app_dir.rglob("*") if f.is_file()]
            total = max(1, len(all_files))

            with zipfile.ZipFile(self._dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, item in enumerate(all_files):
                    arcname = item.relative_to(app_dir)
                    zf.write(item, arcname)
                    pct = int((i + 1) / total * 100)
                    self.progress.emit(pct, item.name)

            size_mb = round(Path(self._dest).stat().st_size / (1024 * 1024), 2)
            self.finished.emit(True, f"Backup saved  ({size_mb} MB)  →  {self._dest}")
        except Exception as e:
            self.finished.emit(False, str(e))


# ── Dialog ────────────────────────────────────────────────────────────

class ExportBackupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Backup")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._worker = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 18, 20, 18)

        title = QLabel("Export Backup")
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#e6edf3;")
        lay.addWidget(title)

        # What gets exported
        info_frame = QFrame()
        info_frame.setObjectName("Card")
        ilay = QVBoxLayout(info_frame)
        ilay.setContentsMargins(14, 12, 14, 12)
        ilay.setSpacing(4)

        ilay.addWidget(QLabel("WHAT WILL BE BACKED UP:").also(
            lambda l: l.setObjectName("SectionLabel")
        ))
        app_dir = get_app_data_dir()
        items = [
            ("mymini3d.db",   "Product library and job history (database)"),
            ("library/",      "All SVG/DXF product files"),
            ("config.json",   "App settings and machine configuration"),
            ("thumbnails/",   "Cached product preview images"),
        ]
        for fname, desc in items:
            row = QHBoxLayout()
            row.setSpacing(8)
            f_lbl = QLabel(fname)
            f_lbl.setStyleSheet(
                "color:#58a6ff; font-size:11px; font-family:Consolas; min-width:110px;"
            )
            d_lbl = QLabel(desc)
            d_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
            row.addWidget(f_lbl)
            row.addWidget(d_lbl, 1)
            ilay.addLayout(row)

        # Data size estimate
        try:
            total_bytes = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file())
            size_str = f"~{round(total_bytes / (1024*1024), 1)} MB"
        except Exception:
            size_str = "unknown size"
        size_lbl = QLabel(f"Estimated zip size: {size_str}")
        size_lbl.setStyleSheet("color:#6e7681; font-size:11px; padding-top:4px;")
        ilay.addWidget(size_lbl)
        lay.addWidget(info_frame)

        # Save location row
        loc_frame, loc_lay = self._section("Save Location")
        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)

        default_name = (
            f"MYMINI3D_Backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        )
        default_path = str(Path.home() / "Desktop" / default_name)
        self._dest_edit = QLineEdit(default_path)
        self._dest_edit.setStyleSheet("font-size:11px;")
        dest_row.addWidget(self._dest_edit, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(72)
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse)
        dest_row.addWidget(browse_btn)
        loc_lay.addLayout(dest_row)
        lay.addWidget(loc_frame)

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

        self._export_btn = QPushButton("Export Backup")
        self._export_btn.setFixedHeight(32)
        self._export_btn.setStyleSheet(
            "background:#238636; color:#fff; border:none; border-radius:4px;"
            "font-size:13px; font-weight:bold; min-height:0; max-height:32px;"
        )
        self._export_btn.clicked.connect(self._start_export)
        btn_row.addWidget(self._export_btn)
        lay.addLayout(btn_row)

    @staticmethod
    def _section(title: str):
        frame = QFrame()
        frame.setObjectName("Card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)
        lbl = QLabel(title.upper())
        lbl.setObjectName("SectionLabel")
        lay.addWidget(lbl)
        return frame, lay

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Backup As",
            self._dest_edit.text(),
            "Zip Archive (*.zip)"
        )
        if path:
            self._dest_edit.setText(path)

    def _start_export(self):
        dest = self._dest_edit.text().strip()
        if not dest:
            QMessageBox.warning(self, "No Destination", "Choose where to save the backup.")
            return

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_lbl.setText("Exporting…")
        self._status_lbl.setStyleSheet("color:#6e7681; font-size:11px;")

        self._worker = _ExportWorker(dest)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, pct: int, fname: str):
        self._progress.setValue(pct)
        self._status_lbl.setText(f"Adding: {fname}")

    def _on_finished(self, ok: bool, msg: str):
        self._progress.setValue(100 if ok else 0)
        self._export_btn.setEnabled(True)
        if ok:
            self._status_lbl.setText(f"✓  {msg}")
            self._status_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
        else:
            self._status_lbl.setText(f"✕  Export failed: {msg}")
            self._status_lbl.setStyleSheet("color:#f85149; font-size:11px;")


# Patch .also()
from PyQt6.QtWidgets import QWidget as _QW
if not hasattr(_QW, "also"):
    def _also(self, fn): fn(self); return self
    _QW.also = _also
