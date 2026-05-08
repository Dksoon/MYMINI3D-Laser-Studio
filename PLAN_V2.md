# MYMINI3D Laser Studio — Version 2 Master Plan
# Updated: 2026-05-08
# Status: PLANNING — not yet started

==============================================================
  VERSION 1 STATUS (all complete, running via python main.py)
==============================================================

UI & Navigation
  [x] Top navigation bar (replaces sidebar)
  [x] Dashboard — live machine + job stats
  [x] Job Sheets page — create, track, quantities
  [x] Library page — product grid, thumbnails
  [x] Machines page — 4-panel K40W style layout
  [x] Settings page — 4 tabs

Machine Control (K40 Whisperer parity)
  [x] Initialize, Home, Unlock Rail
  [x] Jog pad (arrows + dots for diagonal)
  [x] Move To X/Y
  [x] Speed settings per machine (Raster/Vector/Cut)
  [x] Trace Outline (dry run, no laser)
  [x] Start Cut / Stop
  [x] Bed canvas preview (shows SVG design + head position)
  [x] Per-machine settings (General/Raster/Rotary/Advanced — 4 tabs)

Laser Engine
  [x] SVG + DXF file parsing to polylines
  [x] EGV (Lhymicro-GL) encoder — Bresenham line algorithm
  [x] USB K40 driver — connect/disconnect/send
  [x] Mirror Design (flip horizontal)
  [x] Rotate Design (90 degrees)
  [x] X/Y scale factor per machine
  [x] Auto translate design to origin before cutting
  [x] Cutting dialog — real-time progress, multi-step, elapsed time

Job Management
  [x] Create job sheet with products + quantities
  [x] Smart cut: units per sheet, multi-file products
  [x] In Progress tracking — deducts from queue
  [x] Done / Cancel run
  [x] Task queue panel — Pending tab + In Progress tab

Services
  [x] Telegram notifications (job start/end/fail/sheet complete)
  [x] Telegram control bot (/status /queue /jobs /stop /help)
  [x] Google Drive library sync
  [x] Auto-update checker (GitHub releases)
  [x] USB driver auto-installer (Zadig/pnputil)

Packaging (framework ready, data not bundled yet)
  [x] PyInstaller build spec
  [x] Inno Setup installer script
  [x] build.ps1 — one-command build
  [x] App icon generated
  [ ] Bundle user data into installer (Session D)


==============================================================
  VERSION 2 UPGRADE PLAN
==============================================================

-----------------------------------------------------------
SESSION A — Product Library Rebuild (PRIORITY)
-----------------------------------------------------------
Goal: Products have MAIN files + PART files, organized by
      category. User manually controls every tag.

Why needed: Current system is generic. Factory workflow
            requires MAIN (full sheet) vs PART separation.

DB Changes (database.py):
  Product adds:
    - category      : text  e.g. "2026 HOTWHEEL"
    - folder_path   : text  full path to product folder on disk

  ProductFile adds:
    - file_role     : text  "main" or "part"
    - part_name     : text  user-given name e.g. "SIDE LEFT"
    - sheet_number  : int   1, 2, 3... for multi-sheet main files

New Add Product Dialog (add_product_dialog.py — full rebuild):

  Layout:
    Top section:
      Category:     [dropdown of existing] or [+ New Category]
      Product Name: [text field]
      Note: system auto-creates folder on Save:
            %APPDATA%\MYMINI3D\library\[Category]\[Product Name]\

    Main Files section (★):
      Explanation: "These files cut the full product on one sheet.
                   Add multiple if product spans more than one 400x400mm sheet."
      [+ Add Main File] button
      Each row: [★ filename.svg]  Sheet [1]  [Remove]
      Files keep original filename when saved.

    Part Files section (⚙):
      Explanation: "Individual component cuts. Give each part a name."
      [+ Add Part File] button
      Each row: Part Name: [________]  File: [Browse]  [Remove]
      File saved as "[Part Name].svg" inside product folder.

    [Cancel]   [Save Product]
    On Save:
      - Creates category + product folder on disk
      - Copies all files into correct folder
      - Saves Product + ProductFiles to database with roles

Updated Library Page (library_page.py):
  - Products grouped by category (accordion sections)
  - Each product card shows:
      ★ Main files count  |  ⚙ Parts count  |  Category badge
  - Edit product keeps same structure
  - Search works across categories

Files changed:
  app/core/database.py
  app/core/config.py         (add library_root path)
  app/ui/dialogs/add_product_dialog.py   (full rebuild)
  app/ui/pages/library_page.py           (category grouping)

-----------------------------------------------------------
SESSION B — Job Creation with Cut Type
-----------------------------------------------------------
Goal: When adding a product to a job, user chooses:
        FULL SHEET — which main file to use
        INDIVIDUAL — which specific parts to cut

Why needed: Sometimes cut full product (1 sheet operation),
            sometimes cut replacement parts only.

New Job Item Flow:
  Current: [Product] [Quantity]
  New:     [Product] [Quantity] [Cut Type] [File Selection]

  Cut Type = FULL SHEET:
    Dropdown: pick which main file (if product has multiple)
    e.g. "FULL STANDARD (Sheet 1)" or "FULL STANDARD PT2 (Sheet 2)"
    Each unit requires running 1 main file.

  Cut Type = INDIVIDUAL PARTS:
    Checklist: tick which parts to cut this run
    e.g. [x] SIDE LEFT  [x] TOP PANEL  [ ] BASE PLATE
    Each unit = run all ticked files.

DB Changes (database.py):
  JobItem adds:
    - cut_type      : text  "full" or "parts"
    - main_file_id  : int   FK to ProductFile (for full cuts)
    - part_file_ids : text  JSON list of ProductFile IDs (for parts)

Updated Create Job Dialog (create_job_dialog.py):
  - After picking product + qty, shows cut type panel
  - Full: dropdown of main files
  - Parts: checkbox list of part files

Updated Queue Panel (machines_page.py):
  - Shows cut type badge: [★ Full - Sheet 1] or [⚙ Side+Top]

Files changed:
  app/core/database.py
  app/ui/dialogs/create_job_dialog.py
  app/ui/pages/machines_page.py (JobQueuePanel)

-----------------------------------------------------------
SESSION C — Cut Flow Uses Stored File Selection
-----------------------------------------------------------
Goal: When user clicks a job item to cut, the correct
      files are pre-selected based on job type.

Changes:
  Product File Picker (product_file_picker.py):
    - Shows ★ Main files at top (larger, prominent)
    - Shows ⚙ Parts below in a grid
    - If job item already has a file selection, pre-selects it
    - User can override (change file before cutting)

  Cut Dialog (cut_dialog.py):
    - Uses file selection from job item
    - Shows "Sheet 1 of 2" for multi-sheet main files
    - Passes correct files to CuttingDialog

  Cutting Dialog (cutting_dialog.py):
    - "Cutting Sheet 1 of 2: FULL STANDARD.svg"
    - After sheet 1 done: prompts "Load Sheet 2, then click Next"
    - After all sheets done: marks unit complete

Files changed:
  app/ui/dialogs/product_file_picker.py
  app/ui/dialogs/cut_dialog.py
  app/ui/dialogs/cutting_dialog.py

-----------------------------------------------------------
SESSION D — Data Export + EXE Build with Data Bundled
-----------------------------------------------------------
Goal: Everything user added (products, files, database)
      can be packaged into the EXE installer so any
      factory PC gets everything on first install.

Part 1 — Export/Import (for backup + PC-to-PC transfer):
  New: export_backup_dialog.py
    - Packages entire %APPDATA%\MYMINI3D\ into a .zip
    - Includes: database, library files, config, thumbnails
    - Save to any location (Desktop, USB drive, etc.)

  New: import_backup_dialog.py
    - Browse to .zip file
    - Extracts to %APPDATA%\MYMINI3D\
    - Confirmation before overwriting

  Added to Settings page under new "Data" tab.

Part 2 — EXE Build with Pre-loaded Data:
  Updated build.ps1:
    - Detects if %APPDATA%\MYMINI3D\ has data
    - Copies library + database into build package
    - Inno Setup bundles it

  Updated setup.iss:
    - New section: installs pre-populated library folder
    - Installs pre-populated database
    - On UPGRADE: does NOT overwrite existing data (user data safe)
    - On FRESH INSTALL: installs factory data from bundle

  Net result:
    - Build EXE on your PC after adding all products
    - Deploy to any factory machine
    - All products, files, settings appear on first run

Files changed:
  app/ui/dialogs/export_backup_dialog.py  (new)
  app/ui/dialogs/import_backup_dialog.py  (new)
  app/ui/pages/settings_page.py           (add Data tab)
  build.ps1                               (add --include-data flag)
  installer/setup.iss                     (bundle data section)

-----------------------------------------------------------
SESSION E — EXE BUILD WALKTHROUGH (final step)
-----------------------------------------------------------
Prerequisites (before this session):
  1. Sessions A–D all complete
  2. You have added all products via python main.py
  3. All files uploaded, tagged, tested

Step-by-step what happens in this session:
  1. Download + install Inno Setup 6 (one-time, free)
  2. Verify all files in %APPDATA%\MYMINI3D\library\
  3. Run:  .\build.ps1
     - Installs Python packages
     - Generates icon
     - PyInstaller packages app into dist\ folder
     - Inno Setup creates installer .exe in release\ folder
  4. Test installer on a fresh Windows PC (or VM)
  5. Adjust if needed
  6. Final installer file:
       release\MYMINI3D_Laser_Studio_v2.0.0_Setup.exe

Deploy to other factory PCs:
  - Copy Setup.exe to USB
  - Run on each PC
  - All products + data appear automatically
  - No Python required on those machines


==============================================================
  HOW TO RUN NOW (before EXE build)
==============================================================

  1. Double-click:  Run MYMINI3D.bat
     OR open folder in cmd and type:  python main.py

  2. Everything you add (products, jobs, settings) saves to:
     C:\Users\danie\AppData\Roaming\MYMINI3D\

  3. This data WILL be included when we build the EXE

  4. Safe to use and add data at any time — nothing is lost


==============================================================
  VERSION 2 SESSION ORDER
==============================================================

  [ ] Session A  — Product library rebuild (MAIN + PART files)
  [ ] Session B  — Job creation with cut type (Full/Individual)
  [ ] Session C  — Cut flow uses file selection
  [ ] Session D  — Export/Import + EXE build with data
  [ ] Session E  — EXE build walkthrough (done together live)

Start with: "Session A"
