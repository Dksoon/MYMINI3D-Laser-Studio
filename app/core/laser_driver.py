"""
K40 USB laser driver — exact protocol from K40 Whisperer (open-source, GPL).
Vendor: 0x1A86 (CH341), Product: 0x5512

Packet format (34 bytes) — identical to K40 Whisperer:
  [0xA6, 0x00, <30 data bytes padded with 0x46>, 0xA6, OneWireCRC]
"""
from __future__ import annotations
import os
import sys
import time
import threading
from typing import Callable, Optional
from dataclasses import dataclass

try:
    import usb.core
    import usb.util
    import usb.backend.libusb0 as _libusb0_mod   # K40W uses libusb-win32
    import usb.backend.libusb1 as _libusb1_mod   # WinUSB fallback
    USB_AVAILABLE = True
except ImportError:
    USB_AVAILABLE = False


# ── K40 USB identifiers ───────────────────────────────────────────────
K40_VENDOR_ID  = 0x1A86
K40_PRODUCT_ID = 0x5512
ENDPOINT_WRITE = 0x02
ENDPOINT_READ  = 0x82

# ── Packet constants (K40 Whisperer protocol) ─────────────────────────
PACKET_SIZE = 34       # total packet length
HEADER      = 0xA6    # byte 0 and byte 32
FILL_BYTE   = 0x46    # 70 = 'F' — pad unused data bytes
DATA_LEN    = 30      # bytes 2..31
READ_LEN    = 168     # K40 response packet size
TIMEOUT_MS  = 200     # USB timeout (K40W uses 200ms)

# ── Status bytes returned by K40 firmware ────────────────────────────
STATUS_OK       = 206
STATUS_CRC_ERR  = 207
STATUS_BUSY     = 238
STATUS_COMPLETE = 236


# ── libusb DLL search ─────────────────────────────────────────────────

def _exe_dir() -> str:
    return os.path.dirname(os.path.abspath(sys.executable))


def _find_dll(names: list) -> Optional[str]:
    dirs = [
        _exe_dir(),
        getattr(sys, "_MEIPASS", ""),
        r"C:\Program Files\K40 Whisperer",
        r"C:\Program Files\K40 Whisperer\driver\amd64",
        r"C:\Program Files (x86)\K40 Whisperer",
        r"C:\Windows\System32",
        r"C:\Windows\SysWOW64",
    ]
    for d in dirs:
        if not d:
            continue
        for name in names:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def _get_usb_backend():
    if not USB_AVAILABLE:
        return None
    # libusb0 (libusb-win32) — same as K40 Whisperer
    try:
        dll0 = _find_dll(["libusb0.dll", "libusb0_x86.dll"])
        if dll0:
            b = _libusb0_mod.get_backend(find_library=lambda _: dll0)
            if b:
                return b
        b = _libusb0_mod.get_backend()
        if b:
            return b
    except Exception:
        pass
    # libusb1 (WinUSB) fallback
    try:
        dll1 = _find_dll(["libusb-1.0.dll"])
        if dll1:
            b = _libusb1_mod.get_backend(find_library=lambda _: dll1)
            if b:
                return b
        b = _libusb1_mod.get_backend()
        if b:
            return b
    except Exception:
        pass
    return None


_USB_BACKEND = None


# ── Packet building (K40 Whisperer format) ────────────────────────────

def _k40_crc(data: bytes) -> int:
    """OneWire CRC (Dallas/Maxim, 0x8C polynomial) — same as K40 Whisperer."""
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 0x01
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc & 0xFF


def _make_packet(cmd: bytes) -> bytes:
    """
    Build 34-byte K40 packet identical to K40 Whisperer:
      [0xA6, 0x00, cmd_padded_to_30_with_0x46, 0xA6, CRC]
    CRC covers bytes 1..32 (32 bytes).
    """
    packet = bytearray(PACKET_SIZE)
    packet[0]  = HEADER
    packet[1]  = 0x00
    for i in range(DATA_LEN):
        packet[2 + i] = FILL_BYTE
    for i, b in enumerate(cmd[:DATA_LEN]):
        packet[2 + i] = b
    packet[32] = HEADER
    packet[33] = _k40_crc(bytes(packet[1:32]))
    return bytes(packet)


# ── Status / State ────────────────────────────────────────────────────

@dataclass
class LaserStatus:
    connected: bool  = False
    busy:      bool  = False
    error:     bool  = False
    message:   str   = "Disconnected"
    progress:  float = 0.0


# ── Driver ────────────────────────────────────────────────────────────

class K40Driver:
    """Low-level USB driver for one K40 machine. Protocol = K40 Whisperer."""

    def __init__(self, vendor_id: int = K40_VENDOR_ID,
                 product_id: int = K40_PRODUCT_ID,
                 serial: str = "", device_index: int = 0):
        self.vendor_id    = vendor_id
        self.product_id   = product_id
        self.serial       = serial
        self.device_index = device_index   # which K40 to connect to (0=first)
        self._device    = None
        self._lock      = threading.Lock()
        self.status     = LaserStatus()
        self._abort     = False

    # ── Connection ────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not USB_AVAILABLE:
            self.status.message   = "pyusb not installed — simulation mode"
            self.status.connected = True
            return True
        try:
            global _USB_BACKEND
            if _USB_BACKEND is None:
                _USB_BACKEND = _get_usb_backend()

            if _USB_BACKEND is None:
                self.status.message = (
                    "USB backend not found.\n\n"
                    "Go to Machines → Install Driver, then reconnect.\n"
                    "Or use Zadig (zadig.akeo.ie): Options > List All Devices\n"
                    "> select CH341 > WinUSB > Install."
                )
                return False

            # Find all matching K40 devices, pick by index
            all_devs = list(usb.core.find(
                idVendor=self.vendor_id, idProduct=self.product_id,
                backend=_USB_BACKEND, find_all=True
            ))
            if not all_devs:
                self.status.message = (
                    "K40 not found on USB.\n"
                    "Check cable is plugged in and machine is ON."
                )
                return False
            if self.device_index >= len(all_devs):
                self.status.message = (
                    f"USB Device #{self.device_index} not found.\n"
                    f"Only {len(all_devs)} K40 machine(s) connected.\n"
                    "Edit machine settings and set Device # to 0."
                )
                return False

            dev = all_devs[self.device_index]
            if dev is None:
                self.status.message = (
                    "K40 not found on USB.\n"
                    "Check cable is plugged in and machine is ON."
                )
                return False

            # Linux only — skip on Windows
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except Exception:
                pass

            try:
                dev.set_configuration()
            except Exception:
                pass

            # CH341 chip initialization — K40 Whisperer does this
            try:
                dev.ctrl_transfer(0x40, 177, 0x0102, 0, 0, 2000)
            except Exception:
                pass

            try:
                usb.util.claim_interface(dev, 0)
            except Exception:
                pass

            self._device = dev

            # Say hello — get initial status
            self._hello()

            self.status.connected = True
            self.status.message   = "Connected"
            return True

        except Exception as e:
            err = str(e).lower()
            if "13" in str(e) or "access denied" in err or "insufficient" in err:
                self.status.message = (
                    "ACCESS DENIED — wrong USB driver.\n\n"
                    "Click 'Install Driver', unplug USB, plug back in, try again.\n"
                    "Or use Zadig: Options > List All Devices > CH341 > WinUSB."
                )
            else:
                self.status.message = f"Connection error: {e}"
            return False

    def disconnect(self):
        if self._device:
            try:
                usb.util.dispose_resources(self._device)
            except Exception:
                pass
            self._device = None
        self.status.connected = False
        self.status.busy      = False
        self.status.message   = "Disconnected"

    @property
    def is_connected(self) -> bool:
        return self.status.connected

    # ── Low-level I/O ─────────────────────────────────────────────────

    def _hello(self) -> int:
        """Poll machine status via [0xA0] — the only packet that gets a direct response."""
        try:
            with self._lock:
                self._device.write(ENDPOINT_WRITE, bytes([0xA0]), TIMEOUT_MS)
                resp = self._device.read(ENDPOINT_READ, READ_LEN, TIMEOUT_MS)
            return resp[1] if len(resp) > 1 else 0
        except Exception:
            return 0

    def _send_packet(self, cmd: bytes) -> int:
        """
        Write one 34-byte command packet.
        K40 does NOT send a direct response — poll with _hello() for status.
        Returns STATUS_OK if write succeeded, 0 on error.
        """
        if not USB_AVAILABLE or self._device is None:
            return STATUS_OK
        try:
            with self._lock:
                self._device.write(ENDPOINT_WRITE, _make_packet(cmd), TIMEOUT_MS)
            return STATUS_OK
        except Exception:
            return 0

    def _send_cmd(self, cmd: bytes, wait_done: bool = True):
        """Write command then poll until machine is no longer BUSY."""
        if self._send_packet(cmd) == 0:
            return
        if not wait_done:
            return
        for _ in range(60):           # max ~6 seconds
            time.sleep(0.1)
            status = self._hello()
            if status == STATUS_BUSY:
                continue
            break                     # OK, CRC_ERR, COMPLETE, or other

    # ── Machine control (Lhymicro-GL commands) ────────────────────────

    def unlock_rail(self):
        """IS2P — same as K40 Whisperer unlock."""
        self._send_cmd(b"IS2P")

    def home(self):
        """IPP — go to home position (top-right on K40)."""
        self._send_cmd(b"IPP")

    def abort(self):
        """I — emergency stop."""
        self._abort = True
        self._send_cmd(b"I")

    # ── File sending ──────────────────────────────────────────────────

    def send_file_raw(
        self,
        egv_data: bytes,
        on_progress: Optional[Callable[[float], None]] = None,
        on_done:     Optional[Callable[[bool, str], None]] = None,
    ):
        """Send pre-built EGV bytes in a background thread."""
        threading.Thread(
            target=self._send_raw_worker,
            args=(egv_data, on_progress, on_done),
            daemon=True
        ).start()

    def _send_raw_worker(self, egv_data: bytes, on_progress, on_done):
        self._abort          = False
        self.status.busy     = True
        self.status.progress = 0.0
        total = len(egv_data)
        sent  = 0

        try:
            while sent < total and not self._abort:
                piece = egv_data[sent: sent + DATA_LEN]

                # Write packet — no direct response, poll for status
                if self._send_packet(piece) == 0:
                    raise RuntimeError("USB write failed")

                # Poll until machine is ready for next packet
                for _ in range(100):
                    status = self._hello()
                    if status == STATUS_BUSY:
                        time.sleep(0.05)
                        continue
                    if status == STATUS_CRC_ERR:
                        # Retry the packet
                        self._send_packet(piece)
                    break

                sent += len(piece)
                self.status.progress = sent / total * 100
                if on_progress:
                    on_progress(self.status.progress)

            success = not self._abort
            if on_done:
                on_done(success, "Completed" if success else "Cancelled")
        except Exception as e:
            if on_done:
                on_done(False, str(e))
        finally:
            self.status.busy     = False
            self.status.progress = 0.0


# ── Multi-machine manager ─────────────────────────────────────────────

class MachineManager:

    def __init__(self):
        self._drivers: dict[int, K40Driver] = {}

    def get_driver(self, machine_id: int, vendor_id: int = K40_VENDOR_ID,
                   product_id: int = K40_PRODUCT_ID,
                   serial: str = "", device_index: int = 0) -> K40Driver:
        if machine_id not in self._drivers:
            self._drivers[machine_id] = K40Driver(
                vendor_id, product_id, serial, device_index
            )
        return self._drivers[machine_id]

    def connect(self, machine_id: int, **kwargs) -> bool:
        return self.get_driver(machine_id, **kwargs).connect()

    def disconnect(self, machine_id: int):
        if machine_id in self._drivers:
            self._drivers[machine_id].disconnect()

    def disconnect_all(self):
        for d in self._drivers.values():
            d.disconnect()

    def status(self, machine_id: int) -> LaserStatus:
        if machine_id in self._drivers:
            return self._drivers[machine_id].status
        return LaserStatus()

    def send_file(self, machine_id: int, file_path: str, **kwargs):
        drv = self._drivers.get(machine_id)
        if drv and drv.is_connected:
            drv.send_file_raw(b"", **kwargs)
        else:
            raise RuntimeError(f"Machine {machine_id} not connected")


machine_manager = MachineManager()
