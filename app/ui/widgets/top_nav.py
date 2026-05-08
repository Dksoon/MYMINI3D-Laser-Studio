from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtCore import pyqtSignal, Qt
from app import __version__

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("library",   "Library"),
    ("machines",  "Machines"),
    ("settings",  "Settings"),
]


class TopNav(QWidget):
    page_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = ""
        self._buttons: dict[str, QPushButton] = {}
        self.setFixedHeight(38)
        self.setStyleSheet("background:#010409; border-bottom:2px solid #21262d;")
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(0)

        # Logo
        logo = QLabel("MYMINI3D")
        logo.setStyleSheet(
            "color:#58a6ff; font-weight:bold; font-size:14px;"
            "padding:0 16px 0 4px; border:none; background:transparent;"
        )
        lay.addWidget(logo)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background:#21262d; max-width:1px; margin:6px 8px;")
        lay.addWidget(sep)

        # Nav buttons
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("TopNavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setStyleSheet(self._style(False))
            btn.clicked.connect(lambda checked, k=key: self.select(k))
            self._buttons[key] = btn
            lay.addWidget(btn)

        lay.addStretch()

        # Right side: machine status + version
        self._machine_lbl = QLabel("Machines: 0/0")
        self._machine_lbl.setStyleSheet(
            "color:#6e7681; font-size:11px; padding:0 12px; background:transparent;"
        )
        lay.addWidget(self._machine_lbl)

        ver = QLabel(f"v{__version__}")
        ver.setStyleSheet(
            "color:#484f58; font-size:11px; padding:0 8px; background:transparent;"
        )
        lay.addWidget(ver)

    @staticmethod
    def _style(active: bool) -> str:
        if active:
            return (
                "QPushButton{"
                "background:transparent; color:#e6edf3; border:none;"
                "border-bottom:2px solid #58a6ff; font-size:13px;"
                "padding:0 16px; font-weight:bold;}"
            )
        return (
            "QPushButton{"
            "background:transparent; color:#8b949e; border:none;"
            "border-bottom:2px solid transparent; font-size:13px;"
            "padding:0 16px;}"
            "QPushButton:hover{color:#e6edf3; background:#161b22;}"
        )

    def select(self, key: str):
        if key == self._current:
            return
        if self._current in self._buttons:
            self._buttons[self._current].setStyleSheet(self._style(False))
            self._buttons[self._current].setChecked(False)
        self._current = key
        if key in self._buttons:
            self._buttons[key].setStyleSheet(self._style(True))
            self._buttons[key].setChecked(True)
        self.page_changed.emit(key)

    def set_default(self, key: str = "dashboard"):
        self.select(key)

    def update_machine_status(self, online: int, total: int):
        self._machine_lbl.setText(f"Machines: {online}/{total}")
        color = "#3fb950" if online > 0 else "#6e7681"
        self._machine_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; padding:0 12px; background:transparent;"
        )
