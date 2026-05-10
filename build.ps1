# =====================================================================
# MYMINI3D Laser Studio — Full Build Script
# Run from project root:  .\build.ps1
#
# Prerequisites:
#   1. Python 3.11+ in PATH
#   2. pip install -r requirements.txt
#   3. Inno Setup 6 installed (adds ISCC.exe to PATH)
#      Download: https://jrsoftware.org/isdl.php
# =====================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$AppName     = "MYMINI3D Laser Studio"
$Version     = "2.0.7"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  $AppName  v$Version  -  Build Script" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $ProjectRoot

# ── Step 1: Install / update dependencies ────────────────────────────
Write-Host "[1/5] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed" -ForegroundColor Red; exit 1 }
Write-Host "      Done." -ForegroundColor Green

# ── Step 2: Generate icon ─────────────────────────────────────────────
Write-Host "[2/5] Generating app icon..." -ForegroundColor Yellow
python scripts/generate_icon.py
if ($LASTEXITCODE -ne 0) { Write-Host "Icon generation failed" -ForegroundColor Red; exit 1 }
Write-Host "      Done." -ForegroundColor Green

# ── Step 3: Clean previous build ─────────────────────────────────────
Write-Host "[3/5] Cleaning previous build output..." -ForegroundColor Yellow
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist"  }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
Write-Host "      Done." -ForegroundColor Green

# ── Step 4: PyInstaller ───────────────────────────────────────────────
Write-Host "[4/5] Running PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller build.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller failed" -ForegroundColor Red; exit 1 }

$DistExe = "dist\$AppName\$AppName.exe"
if (-not (Test-Path $DistExe)) {
    Write-Host "ERROR: Expected exe not found: $DistExe" -ForegroundColor Red
    exit 1
}
Write-Host "      Built: $DistExe" -ForegroundColor Green

# ── Step 4.4: Bundle master product list (if available) ──────────────
Write-Host "[4.4] Checking for master product list..." -ForegroundColor Yellow
$ProductsFile = "$ProjectRoot\installer\products_default.json"
if (Test-Path $ProductsFile) {
    Copy-Item $ProductsFile "$ProjectRoot\dist\$AppName\products_default.json" -Force
    $ProductCount = (Get-Content $ProductsFile | ConvertFrom-Json).product_count
    Write-Host "      Bundled products_default.json  ($ProductCount products)" -ForegroundColor Green
} else {
    Write-Host "      No products_default.json found — skipping." -ForegroundColor Yellow
    Write-Host "      To bundle products: Settings → Data → Export Product List → save as installer\products_default.json" -ForegroundColor Yellow
}

# ── Step 4.5: Bundle factory data (if available) ─────────────────────
Write-Host "[4.5] Checking for factory data to bundle..." -ForegroundColor Yellow

$AppData       = "$env:APPDATA\MYMINI3D"
$BundleDataDir = "$ProjectRoot\installer\bundled_data"
$BundleFlag    = ""

if (Test-Path "$AppData\mymini3d.db") {
    Write-Host "      Found data at $AppData — bundling into installer..." -ForegroundColor Yellow

    # Clean staging folder
    if (Test-Path $BundleDataDir) { Remove-Item -Recurse -Force $BundleDataDir }
    New-Item -ItemType Directory -Path $BundleDataDir | Out-Null

    # Copy each piece
    Copy-Item "$AppData\mymini3d.db" "$BundleDataDir\mymini3d.db" -ErrorAction SilentlyContinue
    if (Test-Path "$AppData\library")    { Copy-Item "$AppData\library"    "$BundleDataDir\library"    -Recurse -ErrorAction SilentlyContinue }
    if (Test-Path "$AppData\config.json"){ Copy-Item "$AppData\config.json" "$BundleDataDir\config.json" -ErrorAction SilentlyContinue }
    if (Test-Path "$AppData\thumbnails") { Copy-Item "$AppData\thumbnails" "$BundleDataDir\thumbnails" -Recurse -ErrorAction SilentlyContinue }

    $FileCount = (Get-ChildItem $BundleDataDir -Recurse -File -ErrorAction SilentlyContinue).Count
    Write-Host "      Bundled $FileCount files." -ForegroundColor Green
    $BundleFlag = "/DBundleData=1"
} else {
    Write-Host "      No data found — installer will not include pre-loaded products." -ForegroundColor Yellow
    Write-Host "      Add products via the app first, then re-run build.ps1." -ForegroundColor Yellow
    # Clean stale bundled_data so Inno Setup doesn't pick up an old copy
    if (Test-Path $BundleDataDir) { Remove-Item -Recurse -Force $BundleDataDir }
}

# ── Step 5: Inno Setup ───────────────────────────────────────────────
Write-Host "[5/5] Building installer with Inno Setup..." -ForegroundColor Yellow

# Create output folder
if (-not (Test-Path "release")) { New-Item -ItemType Directory "release" | Out-Null }

# Find ISCC.exe
$ISCC = $null
$isccFromPath = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue)
$SearchPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    $(if ($isccFromPath) { $isccFromPath.Source } else { "" })
)
foreach ($p in $SearchPaths) {
    if ($p -and (Test-Path $p)) { $ISCC = $p; break }
}

if (-not $ISCC) {
    Write-Host ""
    Write-Host "  Inno Setup not found." -ForegroundColor Yellow
    Write-Host "  Download from: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    Write-Host "  Then re-run this script to build the installer." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  PyInstaller output is ready at:" -ForegroundColor Cyan
    Write-Host "    dist\$AppName\" -ForegroundColor Cyan
    exit 0
}

& $ISCC "installer\setup.iss" $BundleFlag
if ($LASTEXITCODE -ne 0) { Write-Host "Inno Setup failed" -ForegroundColor Red; exit 1 }

$InstallerPath = "release\MYMINI3D_Laser_Studio_v${Version}_Setup.exe"
if (Test-Path $InstallerPath) {
    $SizeMB = [math]::Round((Get-Item $InstallerPath).Length / 1MB, 1)
    Write-Host "      Installer: $InstallerPath  ($SizeMB MB)" -ForegroundColor Green
}

# ── Done ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "  Installer: release\MYMINI3D_Laser_Studio_v${Version}_Setup.exe" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
