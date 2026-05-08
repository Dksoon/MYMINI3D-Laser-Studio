"""Driver installation dialog — guides user through K40 USB driver setup."""
from __future__ import annotations
import threading
import webbrowser

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from app.core.driver_installer import (
    install_driver_elevated, k40_usb_present, k40_driver_installed, is_admin
)

ZADIG_URL = "https://zadig.akeo.ie"


class DriverInstallDialog(QDialog):
    """
    One-click K40 USB driver installer.
    Tries automated WinUSB install first; falls back to guided Zadig flow.
    """
    driver_installed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install K40 USB Driver")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build()
        self._check_status()

    # ------------------------------------------------------------------ UI

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 20, 24, 20)

        # Title
        title = QLabel("K40 USB Driver Setup")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#e6edf3;")
        lay.addWidget(title)

        sub = QLabel(
            "MYMINI3D will install the USB driver so Windows can talk to your laser."
        )
        sub.setStyleSheet("color:#8b949e; font-size:12px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # Status card
        status_frame = QFrame(); status_frame.setObjectName("Card")
        sf_lay = QVBoxLayout(status_frame)
        sf_lay.setContentsMargins(14, 12, 14, 12)
        sf_lay.setSpacing(8)

        # USB connected row
        usb_row = QHBoxLayout(); usb_row.setSpacing(10)
        self._usb_dot = QLabel("●")
        self._usb_dot.setStyleSheet("color:#6e7681; font-size:16px;")
        self._usb_dot.setFixedWidth(20)
        usb_row.addWidget(self._usb_dot)
        self._usb_lbl = QLabel("Checking for K40 laser…")
        self._usb_lbl.setStyleSheet("color:#8b949e;")
        usb_row.addWidget(self._usb_lbl, 1)
        sf_lay.addLayout(usb_row)

        # Driver row
        drv_row = QHBoxLayout(); drv_row.setSpacing(10)
        self._drv_dot = QLabel("●")
        self._drv_dot.setStyleSheet("color:#6e7681; font-size:16px;")
        self._drv_dot.setFixedWidth(20)
        drv_row.addWidget(self._drv_dot)
        self._drv_lbl = QLabel("Checking driver status…")
        self._drv_lbl.setStyleSheet("color:#8b949e;")
        drv_row.addWidget(self._drv_lbl, 1)
        sf_lay.addLayout(drv_row)

        lay.addWidget(status_frame)

        # Progress bar (hidden until installing)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        # Result label
        self._result_lbl = QLabel()
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setStyleSheet("font-size:12px; padding:4px 0;")
        self._result_lbl.setVisible(False)
        lay.addWidget(self._result_lbl)

        # Steps guide (shown when USB not connected)
        self._guide_frame = QFrame(); self._guide_frame.setObjectName("Card")
        guide_lay = QVBoxLayout(self._guide_frame)
        guide_lay.setContentsMargins(14, 12, 14, 12)
        guide_lay.setSpacing(6)
        guide_title = QLabel("BEFORE YOU CONTINUE")
        guide_title.setObjectName("SectionLabel")
        guide_lay.addWidget(guide_title)
        for step in [
            "1.  Make sure your K40 laser is powered ON",
            "2.  Connect the USB cable from the laser to this PC",
            "3.  Then click  'Install Driver'  below",
        ]:
            lbl = QLabel(step)
            lbl.setStyleSheet("color:#8b949e; font-size:12px;")
            guide_lay.addWidget(lbl)
        self._guide_frame.setVisible(False)
        lay.addWidget(self._guide_frame)

        # Buttons
        btn_row = QHBoxLayout(); btn_row.setSpacing(10)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._close_btn)

        btn_row.addStretch()

        self._zadig_btn = QPushButton("Open Zadig (manual)")
        self._zadig_btn.setToolTip(
            "If automatic install fails, Zadig can install the driver manually."
        )
        self._zadig_btn.setVisible(False)
        self._zadig_btn.clicked.connect(self._open_zadig)
        btn_row.addWidget(self._zadig_btn)

        self._install_btn = QPushButton("Install Driver")
        self._install_btn.setObjectName("PrimaryButton")
        self._install_btn.style().unpolish(self._install_btn)
        self._install_btn.style().polish(self._install_btn)
        self._install_btn.setFixedHeight(34)
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._install)
        btn_row.addWidget(self._install_btn)

        lay.addLayout(btn_row)

    # ------------------------------------------------------------------ status check

    def _check_status(self):
        def _run():
            usb = k40_usb_present()
            drv = k40_driver_installed()
            # Schedule UI update on main thread
            QTimer.singleShot(0, lambda: self._update_status(usb, drv))

        threading.Thread(target=_run, daemon=True).start()

    def _update_status(self, usb_present: bool, driver_ok: bool):
        # USB dot
        if usb_present:
            self._usb_dot.setStyleSheet("color:#3fb950; font-size:16px;")
            self._usb_lbl.setText("K40 laser detected via USB")
            self._usb_lbl.setStyleSheet("color:#3fb950;")
        else:
            self._usb_dot.setStyleSheet("color:#f85149; font-size:16px;")
            self._usb_lbl.setText("K40 not detected — plug in the laser and power it on")
            self._usb_lbl.setStyleSheet("color:#f85149;")
            self._guide_frame.setVisible(True)

        # Driver dot
        if driver_ok:
            self._drv_dot.setStyleSheet("color:#3fb950; font-size:16px;")
            self._drv_lbl.setText("USB driver already installed")
            self._drv_lbl.setStyleSheet("color:#3fb950;")
            self._install_btn.setText("Re-install Driver")
            self._result_lbl.setText(
                "✓  Driver is already installed. Go to Machines and click Connect."
            )
            self._result_lbl.setStyleSheet("color:#3fb950; font-size:12px;")
            self._result_lbl.setVisible(True)
        else:
            self._drv_dot.setStyleSheet("color:#d29922; font-size:16px;")
            self._drv_lbl.setText("USB driver not installed — click Install below")
            self._drv_lbl.setStyleSheet("color:#d29922;")

        self._install_btn.setEnabled(True)

    # ------------------------------------------------------------------ install

    def _install(self):
        self._install_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._result_lbl.setVisible(False)
        self._zadig_btn.setVisible(False)

        def _run():
            ok, msg = install_driver_elevated()
            QTimer.singleShot(0, lambda: self._on_result(ok, msg))

        threading.Thread(target=_run, daemon=True).start()

    def _on_result(self, ok: bool, msg: str):
        self._progress.setVisible(False)
        self._install_btn.setEnabled(True)
        self._result_lbl.setVisible(True)

        if ok:
            self._result_lbl.setText(f"✓  {msg}")
            self._result_lbl.setStyleSheet("color:#3fb950; font-size:12px;")
            self._drv_dot.setStyleSheet("color:#3fb950; font-size:16px;")
            self._drv_lbl.setText("Driver installed successfully")
            self._drv_lbl.setStyleSheet("color:#3fb950;")
            self._install_btn.setText("✓  Done")
            self.driver_installed.emit()
        else:
            self._result_lbl.setText(
                f"Automatic install failed:\n{msg}\n\n"
                "Use 'Open Zadig' as a backup — it takes 30 seconds."
            )
            self._result_lbl.setStyleSheet("color:#f85149; font-size:12px;")
            self._zadig_btn.setVisible(True)

    # ------------------------------------------------------------------ zadig fallback

    def _open_zadig(self):
        webbrowser.open(ZADIG_URL)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Zadig Instructions",
            "Zadig will open in your browser.\n\n"
            "1. Download and run Zadig.exe\n"
            "2. Options → List All Devices\n"
            "3. Select:  USB-EPP/I2C... CH341  (VID: 1A86, PID: 5512)\n"
            "4. Driver:  WinUSB  or  libusb-win32\n"
            "5. Click  Install Driver\n\n"
            "Then close Zadig and click Connect in MYMINI3D."
        )
