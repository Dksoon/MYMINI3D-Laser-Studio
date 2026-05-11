from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QCheckBox, QFileDialog,
    QTabWidget, QFormLayout, QProgressBar, QMessageBox,
    QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from app.core.config import load_config, save_config
from app.services.telegram_service import telegram_service
from app.services.google_drive_service import gdrive_service
from app.services.update_service import update_service
from app import __version__, APP_NAME


# ─────────────────────────────────────────────────────────────
# Reusable section frame
# ─────────────────────────────────────────────────────────────

def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(); frame.setObjectName("Card")
    lay   = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    lbl = QLabel(title.upper())
    lbl.setObjectName("SectionLabel")
    lay.addWidget(lbl)
    return frame, lay

def _row(label: str, widget: QWidget, hint: str = "") -> QHBoxLayout:
    r = QHBoxLayout(); r.setSpacing(12)
    lbl = QLabel(label)
    lbl.setFixedWidth(160)
    lbl.setStyleSheet("color:#8b949e;")
    r.addWidget(lbl)
    r.addWidget(widget, 1)
    if hint:
        h = QLabel(hint); h.setStyleSheet("color:#484f58; font-size:11px;")
        r.addWidget(h)
    return r

def _status_lbl(text: str = "", ok: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{'#3fb950' if ok else '#f85149'}; font-size:12px;")
    return lbl


# ─────────────────────────────────────────────────────────────
# Telegram Tab
# ─────────────────────────────────────────────────────────────

class TelegramTab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(16)

        # How-to card
        how_frame = QFrame(); how_frame.setObjectName("Card")
        how_lay = QVBoxLayout(how_frame)
        how_lay.setContentsMargins(16, 12, 16, 12)
        how_lay.setSpacing(6)
        how_lay.addWidget(QLabel("HOW TO SET UP").also(lambda l: l.setObjectName("SectionLabel")))
        steps = [
            "1.  Open Telegram and search for  @BotFather",
            "2.  Send  /newbot  and follow the prompts to create your bot",
            "3.  Copy the bot token BotFather gives you → paste below",
            "4.  Start a chat with your new bot, then send it any message",
            "5.  Paste your Chat ID (get it from  @userinfobot  → forward a message)",
        ]
        for s in steps:
            lbl = QLabel(s); lbl.setStyleSheet("color:#8b949e; font-size:12px;")
            how_lay.addWidget(lbl)
        lay.addWidget(how_frame)

        # Config section
        cfg_frame, cfg_lay = _section("Configuration")

        self._enabled = QCheckBox("Enable Telegram notifications")
        self._enabled.setChecked(self._cfg.get("telegram_enabled", False))
        cfg_lay.addWidget(self._enabled)

        self._token = QLineEdit(self._cfg.get("telegram_token", ""))
        self._token.setPlaceholderText("123456789:ABCDefGhIJKlmNOPqrSTUVwxYZ")
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        cfg_lay.addLayout(_row("Bot Token", self._token))

        show_btn = QPushButton("Show")
        show_btn.setFixedWidth(60); show_btn.setFixedHeight(28)
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda on: self._token.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        token_row = cfg_lay.itemAt(cfg_lay.count()-1).layout()
        token_row.addWidget(show_btn)

        self._chat_id = QLineEdit(self._cfg.get("telegram_chat_id", ""))
        self._chat_id.setPlaceholderText("-100xxxxxxxxxx  or  xxxxxxxxxx")
        cfg_lay.addLayout(_row("Chat / Group ID", self._chat_id))

        lay.addWidget(cfg_frame)

        # Test section
        test_frame, test_lay = _section("Test Connection")
        test_row = QHBoxLayout(); test_row.setSpacing(10)
        test_btn = QPushButton("Send Test Message")
        test_btn.setObjectName("AccentButton")
        test_btn.style().unpolish(test_btn); test_btn.style().polish(test_btn)
        test_btn.setFixedHeight(32)
        test_btn.clicked.connect(self._test)
        test_row.addWidget(test_btn)
        self._test_status = QLabel()
        self._test_status.setStyleSheet("color:#6e7681; font-size:12px;")
        test_row.addWidget(self._test_status)
        test_row.addStretch()
        test_lay.addLayout(test_row)
        lay.addWidget(test_frame)

        # Control bot status
        bot_frame, bot_lay = _section("Telegram Control Bot")
        self._bot_status = QLabel("Bot not started")
        self._bot_status.setStyleSheet("color:#6e7681; font-size:12px;")
        bot_lay.addWidget(self._bot_status)

        bot_info = QLabel(
            "When enabled, you can send commands to this bot from your phone:\n"
            "/status  /queue  /jobs  /cut  /done  /stop  /help"
        )
        bot_info.setStyleSheet("color:#8b949e; font-size:11px;")
        bot_info.setWordWrap(True)
        bot_lay.addWidget(bot_info)
        lay.addWidget(bot_frame)
        lay.addStretch()

    def _test(self):
        self._test_status.setText("Sending…")
        self._test_status.setStyleSheet("color:#6e7681;")
        telegram_service.configure(
            token=self._token.text().strip(),
            chat_id=self._chat_id.text().strip(),
            enabled=True,
        )
        import asyncio
        loop = asyncio.new_event_loop()
        ok, msg = loop.run_until_complete(
            telegram_service.test_connection()
        )
        loop.close()
        self._test_status.setText("✓ Connected!" if ok else f"✕ {msg}")
        self._test_status.setStyleSheet(
            f"color:{'#3fb950' if ok else '#f85149'}; font-size:12px;"
        )

    def get_values(self) -> dict:
        return {
            "telegram_enabled": self._enabled.isChecked(),
            "telegram_token":   self._token.text().strip(),
            "telegram_chat_id": self._chat_id.text().strip(),
        }


# ─────────────────────────────────────────────────────────────
# Google Drive Tab
# ─────────────────────────────────────────────────────────────

class GDriveTab(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(16)

        # Setup guide
        guide_frame = QFrame(); guide_frame.setObjectName("Card")
        guide_lay = QVBoxLayout(guide_frame)
        guide_lay.setContentsMargins(16, 12, 16, 12)
        guide_lay.setSpacing(6)
        guide_lay.addWidget(QLabel("SETUP STEPS").also(lambda l: l.setObjectName("SectionLabel")))
        for s in [
            "1.  Go to console.cloud.google.com → Create project → Enable Drive API",
            "2.  Credentials → Create OAuth 2.0 Client ID (Desktop app)",
            "3.  Download credentials.json → point to it below",
            "4.  Click 'Authenticate' — browser will open for Google sign-in",
            "5.  Create a folder in Google Drive and paste its ID below",
            "      (Folder ID is the last part of the folder URL)",
        ]:
            lbl = QLabel(s); lbl.setStyleSheet("color:#8b949e; font-size:12px;")
            guide_lay.addWidget(lbl)
        lay.addWidget(guide_frame)

        # Config
        cfg_frame, cfg_lay = _section("Configuration")

        self._enabled = QCheckBox("Enable Google Drive sync")
        self._enabled.setChecked(self._cfg.get("gdrive_enabled", False))
        cfg_lay.addWidget(self._enabled)

        cred_row = QHBoxLayout(); cred_row.setSpacing(8)
        self._cred_path = QLineEdit(self._cfg.get("gdrive_credentials_path", ""))
        self._cred_path.setPlaceholderText("Path to credentials.json…")
        cred_row.addWidget(self._cred_path, 1)
        browse_btn = QPushButton("Browse"); browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_creds)
        cred_row.addWidget(browse_btn)
        cfg_lay.addLayout(_row("credentials.json", QWidget().also(
            lambda w: w.setLayout(cred_row))))

        self._folder_id = QLineEdit(self._cfg.get("gdrive_folder_id", ""))
        self._folder_id.setPlaceholderText("e.g. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms")
        cfg_lay.addLayout(_row("Drive Folder ID", self._folder_id))

        lay.addWidget(cfg_frame)

        # Auth + sync
        act_frame, act_lay = _section("Actions")

        auth_row = QHBoxLayout(); auth_row.setSpacing(10)
        auth_btn = QPushButton("Authenticate with Google")
        auth_btn.setObjectName("AccentButton")
        auth_btn.style().unpolish(auth_btn); auth_btn.style().polish(auth_btn)
        auth_btn.clicked.connect(self._authenticate)
        auth_row.addWidget(auth_btn)
        self._auth_status = QLabel(
            "✓ Already authenticated" if gdrive_service.is_authenticated()
            else "Not authenticated"
        )
        self._auth_status.setStyleSheet(
            f"color:{'#3fb950' if gdrive_service.is_authenticated() else '#6e7681'};"
            "font-size:12px;"
        )
        auth_row.addWidget(self._auth_status)
        auth_row.addStretch()
        act_lay.addLayout(auth_row)

        sync_row = QHBoxLayout(); sync_row.setSpacing(10)
        self._sync_btn = QPushButton("↑  Sync Library to Drive")
        self._sync_btn.setFixedHeight(32)
        self._sync_btn.clicked.connect(self._sync)
        sync_row.addWidget(self._sync_btn)
        dl_btn = QPushButton("↓  Download from Drive")
        dl_btn.setFixedHeight(32)
        dl_btn.clicked.connect(self._download)
        sync_row.addWidget(dl_btn)
        sync_row.addStretch()
        act_lay.addLayout(sync_row)

        self._sync_progress = QProgressBar()
        self._sync_progress.setFixedHeight(6)
        self._sync_progress.setVisible(False)
        act_lay.addWidget(self._sync_progress)

        self._sync_status = QLabel()
        self._sync_status.setStyleSheet("color:#6e7681; font-size:12px;")
        act_lay.addWidget(self._sync_status)

        lay.addWidget(act_frame)
        lay.addStretch()

    def _browse_creds(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select credentials.json", "", "JSON Files (*.json)"
        )
        if path:
            self._cred_path.setText(path)

    def _authenticate(self):
        gdrive_service.configure(
            enabled=True,
            credentials_path=self._cred_path.text().strip(),
            folder_id=self._folder_id.text().strip(),
        )
        ok, msg = gdrive_service.authenticate()
        self._auth_status.setText("✓ Authenticated!" if ok else f"✕ {msg}")
        self._auth_status.setStyleSheet(
            f"color:{'#3fb950' if ok else '#f85149'}; font-size:12px;"
        )

    def _sync(self):
        self._sync_apply_config()
        self._sync_progress.setVisible(True)
        self._sync_progress.setValue(0)
        self._sync_status.setText("Uploading…")

        def _progress(name, done, total):
            pct = int(done / total * 100) if total else 0
            self._sync_progress.setValue(pct)
            self._sync_status.setText(f"Uploading {name}… ({done}/{total})")

        def _done(ok, msg):
            self._sync_progress.setVisible(False)
            self._sync_status.setText(("✓ " if ok else "✕ ") + msg)
            self._sync_status.setStyleSheet(
                f"color:{'#3fb950' if ok else '#f85149'}; font-size:12px;"
            )

        gdrive_service.sync_library(on_progress=_progress, on_done=_done)

    def _download(self):
        self._sync_apply_config()
        self._sync_status.setText("Downloading…")
        gdrive_service.download_library(
            on_done=lambda ok, msg: self._sync_status.setText(
                ("✓ " if ok else "✕ ") + msg
            )
        )

    def _sync_apply_config(self):
        gdrive_service.configure(
            enabled=self._enabled.isChecked(),
            credentials_path=self._cred_path.text().strip(),
            folder_id=self._folder_id.text().strip(),
        )

    def get_values(self) -> dict:
        return {
            "gdrive_enabled":           self._enabled.isChecked(),
            "gdrive_credentials_path":  self._cred_path.text().strip(),
            "gdrive_folder_id":         self._folder_id.text().strip(),
        }


# ─────────────────────────────────────────────────────────────
# Updates Tab
# ─────────────────────────────────────────────────────────────

class UpdatesTab(QWidget):
    _update_signal = pyqtSignal(bool, str, str)   # available, latest_version, dl_url

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg         = cfg
        self._download_url = ""
        self._update_signal.connect(self._on_update_result)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(16)

        cfg_frame, cfg_lay = _section("Update Settings")

        self._auto_check = QCheckBox("Check for updates on startup")
        self._auto_check.setChecked(self._cfg.get("update_check_on_start", True))
        cfg_lay.addWidget(self._auto_check)

        self._update_url = QLineEdit(
            self._cfg.get("update_url",
                          "https://api.github.com/repos/Dksoon/MYMINI3D-Laser-Studio/releases/latest")
        )
        self._update_url.setPlaceholderText("GitHub releases API URL")
        cfg_lay.addLayout(_row("Update URL", self._update_url,
                               "Leave default unless self-hosting releases"))
        lay.addWidget(cfg_frame)

        # Check now
        check_frame, check_lay = _section("Check for Updates")

        check_row = QHBoxLayout(); check_row.setSpacing(10)
        check_btn = QPushButton("Check Now")
        check_btn.setObjectName("AccentButton")
        check_btn.style().unpolish(check_btn); check_btn.style().polish(check_btn)
        check_btn.setFixedHeight(32)
        check_btn.clicked.connect(self._check_now)
        check_row.addWidget(check_btn)
        self._check_status = QLabel(f"Current version: v{__version__}")
        self._check_status.setStyleSheet("color:#6e7681; font-size:12px;")
        check_row.addWidget(self._check_status)
        check_row.addStretch()
        check_lay.addLayout(check_row)

        self._install_btn = QPushButton("⬇  Download & Install Update")
        self._install_btn.setObjectName("PrimaryButton")
        self._install_btn.style().unpolish(self._install_btn)
        self._install_btn.style().polish(self._install_btn)
        self._install_btn.setFixedHeight(34)
        self._install_btn.setVisible(False)
        self._install_btn.clicked.connect(self._install)
        check_lay.addWidget(self._install_btn)

        self._dl_progress = QProgressBar()
        self._dl_progress.setFixedHeight(6)
        self._dl_progress.setVisible(False)
        check_lay.addWidget(self._dl_progress)

        lay.addWidget(check_frame)
        lay.addStretch()

    def _check_now(self):
        update_service.configure(
            update_url=self._update_url.text().strip(),
            auto_check=self._auto_check.isChecked(),
        )
        self._check_status.setText("Checking…")
        self._check_status.setStyleSheet("color:#6e7681; font-size:12px;")
        self._install_btn.setVisible(False)

        # Emit signal from background thread → Qt delivers it on the main thread
        def _result(available, latest, dl_url):
            self._update_signal.emit(available, latest or "", dl_url or "")

        update_service.check_for_update(on_result=_result)

    def _on_update_result(self, available: bool, latest: str, dl_url: str):
        if available:
            self._check_status.setText(
                f"Update available:  v{latest}  →  click below to install"
            )
            self._check_status.setStyleSheet("color:#d29922; font-size:12px;")
            self._download_url = dl_url
            self._install_btn.setVisible(bool(dl_url))
        else:
            self._check_status.setText(
                f"You are on the latest version  (v{__version__})"
            )
            self._check_status.setStyleSheet("color:#3fb950; font-size:12px;")

    def _install(self):
        if not self._download_url:
            return
        self._install_btn.setEnabled(False)
        self._dl_progress.setVisible(True)
        self._dl_progress.setValue(0)
        self._check_status.setText("Downloading installer…")

        def _progress(pct):
            self._dl_progress.setValue(pct)

        def _done(ok, msg):
            self._dl_progress.setVisible(False)
            self._check_status.setText(("✓ " if ok else "✕ ") + msg)
            if ok:
                self._check_status.setStyleSheet("color:#3fb950; font-size:12px;")

        update_service.download_and_install(
            self._download_url,
            on_progress=_progress,
            on_done=_done,
        )

    def get_values(self) -> dict:
        return {
            "update_url":             self._update_url.text().strip(),
            "update_check_on_start":  self._auto_check.isChecked(),
        }


# ─────────────────────────────────────────────────────────────
# Data Tab  (export / import backup)
# ─────────────────────────────────────────────────────────────

class DataTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(16)

        # ── Product List ──────────────────────────────────────────────
        pl_frame, pl_lay = _section("Master Product List")

        pl_info = QLabel(
            "Export your product list to a file. "
            "Save it to  installer\\products_default.json  inside the project folder, "
            "then tell me to build a new installer — all new installations will "
            "come pre-loaded with these products."
        )
        pl_info.setStyleSheet("color:#8b949e; font-size:12px;")
        pl_info.setWordWrap(True)
        pl_lay.addWidget(pl_info)

        pl_btn_row = QHBoxLayout(); pl_btn_row.setSpacing(8)

        exp_pl_btn = QPushButton("↑  Export Product List")
        exp_pl_btn.setFixedHeight(32)
        exp_pl_btn.setStyleSheet(
            "background:#1a2e4a; color:#58a6ff; border:1px solid #1f6feb;"
            "border-radius:4px; font-size:12px; font-weight:bold;"
            "min-height:0; max-height:32px;"
        )
        exp_pl_btn.clicked.connect(self._export_products)
        pl_btn_row.addWidget(exp_pl_btn)

        imp_pl_btn = QPushButton("↓  Import / Sync Product List")
        imp_pl_btn.setFixedHeight(32)
        imp_pl_btn.setStyleSheet(
            "background:#21262d; color:#e6edf3; border:1px solid #30363d;"
            "border-radius:4px; font-size:12px; font-weight:bold;"
            "min-height:0; max-height:32px;"
        )
        imp_pl_btn.clicked.connect(self._import_products)
        pl_btn_row.addWidget(imp_pl_btn)
        pl_btn_row.addStretch()
        pl_lay.addLayout(pl_btn_row)

        self._pl_status = QLabel()
        self._pl_status.setStyleSheet("color:#6e7681; font-size:11px;")
        pl_lay.addWidget(self._pl_status)
        lay.addWidget(pl_frame)

        # ── Export Backup ─────────────────────────────────────────────
        exp_frame, exp_lay = _section("Export Full Backup")

        exp_info = QLabel(
            "Creates a .zip file with everything: database, library files, "
            "settings, and thumbnails.\n"
            "Use this to transfer all data to another PC."
        )
        exp_info.setStyleSheet("color:#8b949e; font-size:12px;")
        exp_info.setWordWrap(True)
        exp_lay.addWidget(exp_info)

        exp_btn_row = QHBoxLayout(); exp_btn_row.setSpacing(10)
        exp_btn = QPushButton("Export Backup…")
        exp_btn.setObjectName("AccentButton")
        exp_btn.style().unpolish(exp_btn); exp_btn.style().polish(exp_btn)
        exp_btn.setFixedHeight(32)
        exp_btn.clicked.connect(self._export)
        exp_btn_row.addWidget(exp_btn)
        exp_btn_row.addStretch()
        exp_lay.addLayout(exp_btn_row)
        lay.addWidget(exp_frame)

        # ── Import Backup ─────────────────────────────────────────────
        imp_frame, imp_lay = _section("Import Full Backup")

        imp_info = QLabel(
            "Restore data from a previously exported .zip backup.\n"
            "This will overwrite all current products, jobs, and settings."
        )
        imp_info.setStyleSheet("color:#8b949e; font-size:12px;")
        imp_info.setWordWrap(True)
        imp_lay.addWidget(imp_info)

        warn_lbl = QLabel("⚠  Import overwrites current data — export a backup first.")
        warn_lbl.setStyleSheet("color:#d29922; font-size:11px;")
        imp_lay.addWidget(warn_lbl)

        imp_btn_row = QHBoxLayout(); imp_btn_row.setSpacing(10)
        imp_btn = QPushButton("Import Backup…")
        imp_btn.setFixedHeight(32)
        imp_btn.setStyleSheet(
            "background:#3a0000; color:#f85149; border:1px solid #b62324;"
            "border-radius:4px; font-size:12px; font-weight:bold;"
            "min-height:0; max-height:32px;"
        )
        imp_btn.clicked.connect(self._import)
        imp_btn_row.addWidget(imp_btn)
        imp_btn_row.addStretch()
        imp_lay.addLayout(imp_btn_row)
        lay.addWidget(imp_frame)

        lay.addStretch()

    # ── product list ──────────────────────────────────────────────────

    def _export_products(self):
        from PyQt6.QtWidgets import QFileDialog
        from app.core.product_sync import export_products
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Product List",
            str(Path.home() / "Downloads" / "products_default.json"),
            "JSON Files (*.json)"
        )
        if not path:
            return
        ok, msg = export_products(path)
        self._pl_status.setText(("✓ " if ok else "✕ ") + msg)
        self._pl_status.setStyleSheet(
            f"color:{'#3fb950' if ok else '#f85149'}; font-size:11px;"
        )

    def _import_products(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from app.core.product_sync import import_products
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Product List", "", "JSON Files (*.json)"
        )
        if not path:
            return

        reply = QMessageBox(self)
        reply.setWindowTitle("Import Product List")
        reply.setText(
            "How would you like to import?\n\n"
            "• Merge — add any missing products, keep your existing ones\n"
            "• Sync  — delete all current products and replace with the file"
        )
        reply.addButton("Merge (safe)", QMessageBox.ButtonRole.AcceptRole)
        sync_btn = reply.addButton("Sync (replace all)", QMessageBox.ButtonRole.DestructiveRole)
        reply.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        reply.exec()

        clicked = reply.clickedButton()
        if clicked is None or reply.buttonRole(clicked) == QMessageBox.ButtonRole.RejectRole:
            return

        replace_all = (clicked is sync_btn)
        ok, msg = import_products(path, replace_all=replace_all)
        self._pl_status.setText(("✓ " if ok else "✕ ") + msg)
        self._pl_status.setStyleSheet(
            f"color:{'#3fb950' if ok else '#f85149'}; font-size:11px;"
        )

    # ── full backup ───────────────────────────────────────────────────

    def _export(self):
        from app.ui.dialogs.export_backup_dialog import ExportBackupDialog
        ExportBackupDialog(self).exec()

    def _import(self):
        from app.ui.dialogs.import_backup_dialog import ImportBackupDialog
        ImportBackupDialog(self).exec()

    def get_values(self) -> dict:
        return {}


# ─────────────────────────────────────────────────────────────
# About Tab
# ─────────────────────────────────────────────────────────────

class AboutTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 32, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        name = QLabel("MYMINI3D Laser Studio")
        name.setStyleSheet(
            "font-size:24px; font-weight:bold; color:#e6edf3;"
        )
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)

        ver = QLabel(f"Version  {__version__}")
        ver.setStyleSheet("color:#58a6ff; font-size:14px;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

        lay.addSpacing(20)

        for line, color in [
            ("Multi-machine K40 laser cutter management", "#8b949e"),
            ("Job sheets · File library · Telegram notifications · Google Drive sync", "#6e7681"),
            ("", ""),
            ("Built with Python · PyQt6 · SQLAlchemy", "#484f58"),
            ("Laser protocol based on K40 Whisperer (GPL v3)", "#484f58"),
        ]:
            lbl = QLabel(line)
            lbl.setStyleSheet(f"color:{color}; font-size:12px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)

        lay.addSpacing(24)

        data_frame, data_lay = _section("Data Location")
        from app.core.config import get_app_data_dir
        path_lbl = QLabel(str(get_app_data_dir()))
        path_lbl.setStyleSheet(
            "color:#58a6ff; font-size:12px; font-family:Consolas,monospace;"
        )
        path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        data_lay.addWidget(path_lbl)
        hint = QLabel(
            "All settings, database and library files are stored here.\n"
            "Installing an update will NOT delete this folder."
        )
        hint.setStyleSheet("color:#6e7681; font-size:11px;")
        data_lay.addWidget(hint)
        lay.addWidget(data_frame)
        lay.addStretch()

    def get_values(self) -> dict:
        return {}


# ─────────────────────────────────────────────────────────────
# Main Settings Page
# ─────────────────────────────────────────────────────────────

# Monkey-patch also() helper onto QWidget so we can chain calls inline
def _also(self, fn):
    fn(self); return self
QWidget.also = _also


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = load_config()
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame(); header.setObjectName("HeaderBar")
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 16, 24, 12)
        title_col = QVBoxLayout()
        title = QLabel("Settings"); title.setObjectName("PageTitle")
        title_col.addWidget(title)
        sub = QLabel("Telegram, Google Drive, updates, data backup and app info")
        sub.setObjectName("PageSubtitle")
        title_col.addWidget(sub)
        h.addLayout(title_col); h.addStretch()

        save_btn = QPushButton("💾  Save Settings")
        save_btn.setObjectName("PrimaryButton")
        save_btn.style().unpolish(save_btn); save_btn.style().polish(save_btn)
        save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._save)
        h.addWidget(save_btn)
        root.addWidget(header)

        # Scroll area
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); content.setStyleSheet("background:#0d1117;")
        clay = QVBoxLayout(content)
        clay.setContentsMargins(24, 20, 24, 24)

        # Tabs
        tabs = QTabWidget()
        self._telegram_tab = TelegramTab(self._cfg)
        self._gdrive_tab   = GDriveTab(self._cfg)
        self._updates_tab  = UpdatesTab(self._cfg)
        self._data_tab     = DataTab()
        self._about_tab    = AboutTab()

        tabs.addTab(self._telegram_tab, "Notifications")
        tabs.addTab(self._gdrive_tab,   "Google Drive")
        tabs.addTab(self._updates_tab,  "Updates")
        tabs.addTab(self._data_tab,     "Data")
        tabs.addTab(self._about_tab,    "About")

        clay.addWidget(tabs)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # Status bar message
        self._save_status = QLabel()
        self._save_status.setStyleSheet(
            "color:#3fb950; font-size:12px; padding:6px 24px;"
        )
        root.addWidget(self._save_status)

    def _save(self):
        self._cfg.update(self._telegram_tab.get_values())
        self._cfg.update(self._gdrive_tab.get_values())
        self._cfg.update(self._updates_tab.get_values())
        save_config(self._cfg)

        # Apply live
        token   = self._cfg["telegram_token"]
        chat_id = self._cfg["telegram_chat_id"]
        enabled = self._cfg["telegram_enabled"]

        telegram_service.configure(token=token, chat_id=chat_id, enabled=enabled)

        # Restart control bot with new settings
        from app.services.telegram_bot import telegram_bot
        telegram_bot.configure(token=token, chat_id=chat_id, enabled=enabled)

        # Update bot status label
        if hasattr(self._telegram_tab, "_bot_status"):
            if enabled and token and chat_id:
                self._telegram_tab._bot_status.setText("✓ Control bot running")
                self._telegram_tab._bot_status.setStyleSheet(
                    "color:#3fb950; font-size:12px;"
                )
            else:
                self._telegram_tab._bot_status.setText(
                    "Bot disabled — enable notifications and enter token/chat ID"
                )
                self._telegram_tab._bot_status.setStyleSheet(
                    "color:#6e7681; font-size:12px;"
                )
        gdrive_service.configure(
            enabled=self._cfg["gdrive_enabled"],
            credentials_path=self._cfg["gdrive_credentials_path"],
            folder_id=self._cfg["gdrive_folder_id"],
        )
        update_service.configure(
            update_url=self._cfg["update_url"],
            auto_check=self._cfg["update_check_on_start"],
        )

        self._save_status.setText("✓  Settings saved")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self._save_status.setText(""))

    def showEvent(self, event):
        super().showEvent(event)
        self._cfg = load_config()
