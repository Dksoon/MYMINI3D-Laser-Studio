from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtCore import pyqtSignal, Qt
from app import __version__


NAV_ITEMS = [
    ("dashboard",  "  ⌂  Dashboard"),
    ("jobs",       "  ▦  Job Sheets"),
    ("library",    "  ▤  Library"),
    ("machines",   "  ⎔  Machines"),
    ("settings",   "  ⚙  Settings"),
]


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)   # emits page key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._buttons: dict[str, QPushButton] = {}
        self._current = ""
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("MYMINI3D")
        logo.setObjectName("SidebarLogo")
        layout.addWidget(logo)

        sub = QLabel("Laser Studio")
        sub.setObjectName("SidebarSubtitle")
        layout.addWidget(sub)

        # Divider
        layout.addWidget(self._divider())

        layout.addSpacing(8)

        # Nav buttons
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setProperty("active", "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.select(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        layout.addWidget(self._divider())

        # Version
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("SidebarVersion")
        layout.addWidget(ver)

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("SidebarDivider")
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    def select(self, key: str):
        if key == self._current:
            return
        # deactivate old
        if self._current in self._buttons:
            b = self._buttons[self._current]
            b.setProperty("active", "false")
            b.style().unpolish(b)
            b.style().polish(b)
        # activate new
        self._current = key
        if key in self._buttons:
            b = self._buttons[key]
            b.setProperty("active", "true")
            b.style().unpolish(b)
            b.style().polish(b)
        self.page_changed.emit(key)

    def set_default(self, key: str = "dashboard"):
        self.select(key)
