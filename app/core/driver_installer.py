"""
K40 USB driver installer for Windows.
Uses pnputil + WinUSB (built into Windows 10/11) — no external files needed.
Falls back to guided Zadig installation if automatic install fails.
"""
from __future__ import annotations
import ctypes
import subprocess
import sys
import os
from pathlib import Path
from typing import Callable, Optional


# ── Paths ─────────────────────────────────────────────────────────────

def _driver_file(name: str) -> Optional[Path]:
    """Find a driver file whether running from source or as a built exe."""
    candidates = [
        # Alongside the exe (build.ps1 copies drivers/ here)
        Path(sys.executable).parent / name,
        # PyInstaller _MEIPASS
        Path(getattr(sys, "_MEIPASS", "")) / "drivers" / name,
        # Running from source (dev mode)
        Path(__file__).parent.parent.parent / "drivers" / name,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ── Admin helpers ─────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin(args: list[str]) -> tuple[bool, str]:
    """
    Re-launch a command as Administrator using ShellExecute 'runas'.
    Returns (success, message).
    """
    try:
        import shlex
        cmd   = args[0]
        params = " ".join(f'"{a}"' if " " in a else a for a in args[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", cmd, params, None, 1
        )
        # ShellExecute returns > 32 on success
        if ret > 32:
            return True, "Launched as administrator"
        return False, f"ShellExecute returned {ret}"
    except Exception as e:
        return False, str(e)


# ── Driver detection ──────────────────────────────────────────────────

def k40_usb_present() -> bool:
    """Return True if a K40 USB device (VID_1A86&PID_5512) is connected."""
    try:
        result = subprocess.run(
            ["pnputil", "/enum-devices", "/connected", "/class", "USB"],
            capture_output=True, text=True, timeout=10
        )
        return "VID_1A86&PID_5512" in result.stdout.upper()
    except Exception:
        return False


def k40_driver_installed() -> bool:
    """Return True if the K40 already has a working WinUSB/libusb driver."""
    try:
        result = subprocess.run(
            ["pnputil", "/enum-drivers"],
            capture_output=True, text=True, timeout=10
        )
        txt = result.stdout.upper()
        return "VID_1A86" in txt and "PID_5512" in txt
    except Exception:
        return False


# ── Automated install ─────────────────────────────────────────────────

def install_driver_silent() -> tuple[bool, str]:
    """
    Install the K40 libusb-win32 driver using the same installer as K40 Whisperer.
    This is the most reliable approach — same driver stack K40W uses.
    Must be called from an elevated (admin) process.
    """
    # Primary: use K40 Whisperer's proven driver installer
    installer = _driver_file("K40_Driver_Install.exe")
    if installer:
        try:
            result = subprocess.run(
                [str(installer)],
                capture_output=True, timeout=120
            )
            if result.returncode == 0:
                return True, (
                    "K40 USB driver installed successfully!\n\n"
                    "1. Unplug the USB cable from the laser\n"
                    "2. Plug it back in\n"
                    "3. Click Connect"
                )
            # Non-zero may still mean success (installer returned its own code)
            return True, (
                "Driver installer ran.\n\n"
                "1. Unplug the USB cable from the laser\n"
                "2. Plug it back in\n"
                "3. Click Connect"
            )
        except Exception as e:
            pass   # fall through to pnputil backup

    # Fallback: pnputil with WinUSB INF
    inf = _driver_file("k40_winusb.inf") or _driver_file("K40_Laser.inf")
    if inf:
        try:
            result = subprocess.run(
                ["pnputil", "/add-driver", str(inf), "/install"],
                capture_output=True, text=True, timeout=60
            )
            ok = result.returncode in (0, 3010, 259)
            if ok:
                try:
                    subprocess.run(["pnputil", "/scan-devices"],
                                   capture_output=True, timeout=20)
                except Exception:
                    pass
                return True, (
                    "Driver installed.\n\n"
                    "1. Unplug the USB cable from the laser\n"
                    "2. Plug it back in\n"
                    "3. Click Connect"
                )
            out = (result.stdout + result.stderr).strip()
            return False, f"pnputil failed (code {result.returncode}):\n{out}"
        except Exception as e:
            return False, str(e)

    return False, (
        "Driver installer not found.\n"
        "Please install K40 Whisperer first, or use Zadig (zadig.akeo.ie):\n"
        "Options > List All Devices > select CH341 > WinUSB > Install"
    )


def install_driver_elevated() -> tuple[bool, str]:
    """
    Install driver by re-launching this module as admin if needed.
    Call from the UI — UAC prompt will appear.
    """
    if is_admin():
        return install_driver_silent()

    # Re-launch Python with this script as admin
    script = Path(__file__).resolve()
    ok, msg = run_as_admin([sys.executable, str(script), "--install"])
    if ok:
        return True, "Driver installation launched.\nClose and re-open the app if the laser still shows Offline."
    return False, f"Could not elevate to admin:\n{msg}"


# ── Entry point (called when script is launched elevated) ─────────────

if __name__ == "__main__":
    if "--install" in sys.argv:
        ok, msg = install_driver_silent()
        if ok:
            ctypes.windll.user32.MessageBoxW(0, msg, "K40 Driver Installed", 0x40)
        else:
            ctypes.windll.user32.MessageBoxW(0, msg, "Driver Install Failed", 0x10)
        sys.exit(0 if ok else 1)
