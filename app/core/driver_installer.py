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

def _inf_path() -> Path:
    """Find the bundled .inf file whether running from source or as a built .exe."""
    candidates = [
        # Running from source
        Path(__file__).parent.parent.parent / "drivers" / "k40_winusb.inf",
        # Bundled by PyInstaller (_MEIPASS)
        Path(getattr(sys, "_MEIPASS", "")) / "drivers" / "k40_winusb.inf",
        # Alongside the .exe
        Path(sys.executable).parent / "drivers" / "k40_winusb.inf",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]   # return first even if missing — error handled later


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
    Install the K40 WinUSB driver silently.
    Must be called from an elevated (admin) process.
    Returns (success, message).
    """
    inf = _inf_path()
    if not inf.exists():
        return False, f"Driver file not found:\n{inf}"

    try:
        result = subprocess.run(
            ["pnputil", "/add-driver", str(inf), "/install"],
            capture_output=True, text=True, timeout=60
        )
        out = (result.stdout + result.stderr).strip()

        # Exit code 0 = success, 3010 = success + reboot needed
        if result.returncode in (0, 3010):
            msg = "Driver installed successfully."
            if result.returncode == 3010:
                msg += "\n\nA restart may be needed — usually not required."
            return True, msg

        # Exit code 259 = driver already present (also fine)
        if result.returncode == 259 or "already installed" in out.lower():
            return True, "Driver already installed."

        return False, f"pnputil failed (code {result.returncode}):\n{out}"
    except FileNotFoundError:
        return False, "pnputil not found — requires Windows 10/11."
    except Exception as e:
        return False, str(e)


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
