"""Temporary placeholder pages for phases 3-6 (will be replaced)."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt


class PlaceholderPage(QWidget):
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("HeaderBar")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(24, 16, 24, 12)
        hlay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        hlay.addWidget(t)
        s = QLabel(description)
        s.setObjectName("PageSubtitle")
        hlay.addWidget(s)
        lay.addWidget(header)

        body = QWidget()
        blay = QVBoxLayout(body)
        blay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg = QLabel(f"⚙  {title} — Coming in next phase")
        msg.setStyleSheet("color: #6e7681; font-size: 15px;")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        blay.addWidget(msg)
        lay.addWidget(body, 1)
