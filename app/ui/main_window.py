from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QStatusBar, QLabel
)
from PyQt6.QtCore import Qt, QTimer

from app.ui.widgets.top_nav      import TopNav
from app.ui.pages.dashboard_page  import DashboardPage
from app.ui.pages.library_page    import LibraryPage
from app.ui.pages.machines_page   import MachinesPage
from app.ui.pages.settings_page   import SettingsPage
from app.core.database  import init_db
from app.core.config    import load_config
from app.services.telegram_service import telegram_service
from app.services.telegram_bot     import telegram_bot
from app.services.update_service   import update_service
from app import APP_NAME, __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._cfg = load_config()
        init_db()
        self._setup_services()
        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------ setup

    def _setup_services(self):
        token   = self._cfg.get("telegram_token", "")
        chat_id = self._cfg.get("telegram_chat_id", "")
        enabled = self._cfg.get("telegram_enabled", False)

        telegram_service.configure(token=token, chat_id=chat_id, enabled=enabled)

        # Start control bot if configured
        telegram_bot.configure(token=token, chat_id=chat_id, enabled=enabled)
        update_service.configure(
            update_url = self._cfg.get("update_url", ""),
            auto_check = self._cfg.get("update_check_on_start", True),
        )
        if self._cfg.get("update_check_on_start", True):
            update_service.check_for_update(on_result=self._on_update_result)

    def _apply_theme(self):
        qss = Path(__file__).parent.parent / "resources" / "styles" / "theme.qss"
        if qss.exists():
            css = qss.read_text(encoding="utf-8")
            # Apply to QApplication so ALL widgets (including dialogs) get the theme
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().setStyleSheet(css)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        self.setWindowTitle(f"{APP_NAME}  v{__version__}")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)

        # Root widget — vertical stack: TopNav → pages
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top navigation bar (replaces sidebar)
        self._nav = TopNav()
        self._nav.page_changed.connect(self._switch_page)
        root.addWidget(self._nav)

        # Stacked pages — full width below the nav bar
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Register pages
        self._pages: dict[str, QWidget] = {}
        self._add_page("dashboard", DashboardPage())
        self._add_page("library",   LibraryPage())
        self._add_page("machines",  MachinesPage())
        self._add_page("settings",  SettingsPage())

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel(f"  {APP_NAME}  |  Ready")
        self._status_bar.addWidget(self._status_label)
        self._machine_status_label = QLabel()
        self._status_bar.addPermanentWidget(self._machine_status_label)

        # Default page
        self._nav.set_default("machines")

        # Refresh timer
        self._sb_timer = QTimer(self)
        self._sb_timer.timeout.connect(self._refresh_status)
        self._sb_timer.start(5000)
        self._refresh_status()

        # Startup product-sync check — runs 2 s after window opens
        QTimer.singleShot(2000, self._check_bundled_products)

    def _add_page(self, key: str, widget: QWidget):
        self._pages[key] = widget
        self._stack.addWidget(widget)

    def _switch_page(self, key: str):
        if key in self._pages:
            self._stack.setCurrentWidget(self._pages[key])

    # ------------------------------------------------------------------ status

    def _refresh_status(self):
        from app.core.database import get_session, Machine, MachineStatus
        from app.core.laser_driver import machine_manager
        with get_session() as s:
            machines = s.query(Machine).all()
        online = sum(1 for m in machines if machine_manager.status(m.id).connected)
        total  = len(machines)
        self._machine_status_label.setText(
            f"Machines: {online}/{total} online  |  v{__version__}  "
        )
        self._nav.update_machine_status(online, total)

    def _on_update_result(self, available: bool, latest: str, url: str):
        if available:
            self._status_label.setText(
                f"  ⬆  Update available: v{latest}  —  go to Settings → Updates"
            )
            self._status_label.setStyleSheet("color:#d29922;")

    def _check_bundled_products(self):
        from app.core.product_sync import bundled_path, bundled_hash, bundled_count
        from app.core.config import load_config, save_config
        p = bundled_path()
        if not p:
            return
        current_hash = bundled_hash()
        cfg = load_config()
        if cfg.get("last_product_sync_hash") == current_hash:
            return  # already handled this version

        count = bundled_count()
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Product List Update")
        msg.setText(
            f"A master product list is available ({count} products).\n\n"
            "What would you like to do?"
        )
        msg.setInformativeText(
            "• Keep my products — your current list stays unchanged\n"
            "• Sync — delete your current products and load the master list\n\n"
            "Your jobs and task queue are never affected."
        )
        keep_btn = msg.addButton("Keep my products", QMessageBox.ButtonRole.RejectRole)
        sync_btn = msg.addButton("Sync product list", QMessageBox.ButtonRole.DestructiveRole)
        msg.setDefaultButton(keep_btn)
        msg.exec()

        if msg.clickedButton() is sync_btn:
            from app.core.product_sync import import_products
            ok, result = import_products(str(p), replace_all=True)
            if ok:
                self._status_label.setText(f"  ✓  {result}")
                self._status_label.setStyleSheet("color:#3fb950;")
                # Refresh library if open
                lib = self._pages.get("library")
                if lib and hasattr(lib, "refresh"):
                    lib.refresh()

        # Mark as handled regardless of choice
        cfg["last_product_sync_hash"] = current_hash
        save_config(cfg)

    # ------------------------------------------------------------------ close

    def closeEvent(self, event):
        from app.core.laser_driver import machine_manager
        machine_manager.disconnect_all()
        super().closeEvent(event)
