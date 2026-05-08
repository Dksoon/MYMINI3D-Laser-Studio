# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MYMINI3D Laser Studio
# Build with:  pyinstaller build.spec

import sys
from pathlib import Path

APP_NAME    = "MYMINI3D Laser Studio"
ENTRY_POINT = "main.py"
ICON_PATH   = "installer/icon.ico"

block_cipher = None

# ── Data files bundled into the exe ───────────────────────────────────
datas = [
    # QSS theme
    ("app/resources/styles/theme.qss", "app/resources/styles"),
    # Icons folder
    ("app/resources/icons",            "app/resources/icons"),
    # K40 USB driver INF (used by driver_installer.py)
    ("drivers/k40_winusb.inf",         "drivers"),
]

# ── Hidden imports not auto-detected by PyInstaller ───────────────────
hidden = [
    # SQLAlchemy
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.orm",
    "sqlalchemy.orm.decl_api",
    "sqlalchemy.ext.declarative",
    # PyQt6
    "PyQt6.QtCore",
    "PyQt6.QtWidgets",
    "PyQt6.QtGui",
    "PyQt6.sip",
    # PIL/Pillow
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.PngImagePlugin",
    # packaging
    "packaging.version",
    # App services (dynamic imports)
    "app.services.telegram_service",
    "app.services.google_drive_service",
    "app.services.update_service",
]

# ── Modules to exclude (reduces size) ─────────────────────────────────
excludes = [
    "tkinter", "_tkinter",
    "unittest", "doctest",
    "pdb", "profile", "pstats",
    "http.server",
    "xmlrpc", "ftplib", "imaplib",
    "multiprocessing",
    "numpy", "pandas", "scipy",
    "matplotlib",          # heavy; only needed for DXF thumbs (optional)
    "notebook", "IPython",
    # Exclude PyQt5 — we use PyQt6 only (both can't coexist in frozen app)
    "PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui",
    "PyQt5.sip", "PyQt5.Qt5",
]

a = Analysis(
    [ENTRY_POINT],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                  # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    name=APP_NAME,
)
