# MYMINI3D Laser Studio — Build Plan

## Tech Stack
- Python 3.11 + PyQt6 (UI)
- SQLite + SQLAlchemy (database)
- PyInstaller + Inno Setup (single .exe installer)
- python-telegram-bot (notifications)
- Google Drive API (file sync)
- App data in %APPDATA%\MYMINI3D\ (survives updates)

## Phase 1 — Foundation (DONE)
- [x] requirements.txt
- [x] app/__init__.py
- [x] app/core/config.py       — paths, config load/save
- [x] app/core/database.py     — all SQLAlchemy models
- [x] app/core/laser_driver.py — USB K40 driver + MachineManager
- [x] app/services/telegram_service.py

## Phase 2 — UI Shell (DONE)
- [x] app/resources/styles/theme.qss   — dark pro theme
- [x] app/ui/main_window.py            — main window + nav
- [x] app/ui/widgets/sidebar.py        — left nav sidebar
- [x] app/ui/pages/dashboard_page.py   — overview cards
- [x] app/ui/pages/placeholder_page.py — temp stubs for phases 3-6
- [x] main.py                          — entry point

## Phase 3 — Job Sheets (DONE)
- [x] app/ui/pages/job_sheets_page.py   — split panel: list + detail view
- [x] app/ui/dialogs/job_sheet_dialog.py — create/edit with due date
- [x] app/ui/dialogs/add_item_dialog.py  — add product + qty (shows sheets calc)
- [x] app/ui/dialogs/cut_dialog.py       — smart cut + CompleteRunDialog

## Phase 4A — Library Backend (DONE)
- [x] app/core/svg_utils.py            — thumbnail gen (cairosvg → PIL fallback)
- [x] app/ui/dialogs/add_product_dialog.py — create/edit product, ordered files, copy to library

## Phase 4B — Library UI (DONE)
- [x] app/ui/pages/library_page.py     — product grid, search, filter, thumbnail cards, wired into main window

## Phase 5 — Machines (DONE)
- [x] app/ui/dialogs/machine_dialog.py  — add/edit machine (name, USB IDs, bed size)
- [x] app/ui/pages/machines_page.py     — connect/disconnect, live status, progress bar

## Phase 6 — Services (DONE)
- [x] app/services/google_drive_service.py  — OAuth2 auth, upload/download/sync
- [x] app/services/update_service.py        — GitHub release check, download + run installer
- [x] app/ui/pages/settings_page.py         — 4-tab settings: Notifications, Google Drive, Updates, About

## Phase 7 — Packaging (DONE)
- [x] scripts/generate_icon.py         — generates installer/icon.ico (run once)
- [x] build.spec                       — PyInstaller one-folder build
- [x] installer/setup.iss             — Inno Setup: silent update, preserves %APPDATA%
- [x] build.ps1                        — one-command full build script

## Phase 8 — Laser Engine (IN PROGRESS)

### Phase 8A (DONE)
- [x] app/core/svg_to_path.py   — SVG+DXF → polylines (mm), full curve flattening
- [x] app/core/egv_writer.py    — polylines → EGV bytes (Lhymicro-GL, Bresenham)
- [x] app/core/laser_job.py     — job orchestrator: file→EGV→USB, trace/cut/jog/stop
- [x] app/core/laser_driver.py  — added send_file_raw() for pre-built EGV data

### Phase 8B (DONE)
- [x] app/ui/pages/machine_control_page.py — K40-style control panel per machine
      Initialize · Home · Unlock · Jog pad · Move To · Speed settings
      SVG preview · Trace Outline · STOP button · Position status
- [x] machines_page.py updated — "⚙ Control" button on each machine card

### Phase 8C (DONE)
- [x] app/ui/dialogs/cutting_dialog.py — real-time progress, multi-step, elapsed timer
- [x] cut_dialog.py updated — ✂ Cut fires real LaserJob, graceful fallback if not connected
- [x] Telegram fires on real job start, complete, fail, sheet done
- [x] config.py — default speed settings (cut 8mm/s, vector 20mm/s, raster 200mm/s)

## STATUS: FULLY COMPLETE — ALL PHASES DONE

## Key Design Decisions
- Each product has: units_per_sheet + multiple ordered files
- Cut dialog: pick qty → shows sheets needed → moves to In Progress
- Cancel run → qty returns to pending
- Telegram fires on: job start, job end, job fail, sheet complete
- Google Drive syncs the /library folder only
- Auto-update: check GitHub releases, download new .exe installer, run silently
- Multi-machine: each machine gets its own tab, 10 slots pre-wired
