"""
K40 / Lhymicro-GL USB laser driver.
Implements the same USB protocol as K40 Whisperer (open-source, GPL).
Vendor: 0x1a86 (CH341), Product: 0x5512
"""
from __future__ import annotations
import time
import threading
from typing import Callable, Optional
from dataclasses import dataclass, field

try:
    import usb.core
    import usb.util
    USB_AVAILABLE = True
except ImportError:
    USB_AVAILABLE = False

# K40 USB identifiers
K40_VENDOR_ID  = 0x1A86
K40_PRODUCT_ID = 0x5512
ENDPOINT_WRITE = 0x02
ENDPOINT_READ  = 0x82
PACKET_SIZE    = 30

STATUS_OK       = 206
STATUS_CRC_ERR  = 207
STATUS_BUSY     = 238
STATUS_COMPLETE = 236


@dataclass
class LaserStatus:
    connected: bool = False
    busy: bool = False
    error: bool = False
    message: str = "Disconnected"
    progress: float = 0.0


class K40Driver:
    """Low-level USB driver for a single K40 laser machine."""

    def __init__(self, vendor_id: int = K40_VENDOR_ID, product_id: int = K40_PRODUCT_ID,
                 serial: str = ""):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.serial = serial
        self._device = None
        self._lock = threading.Lock()
        self.status = LaserStatus()
        self._abort = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        if not USB_AVAILABLE:
            self.status.message = "pyusb not installed — simulation mode"
            self.status.connected = True
            return True
        try:
            kwargs = {"idVendor": self.vendor_id, "idProduct": self.product_id}
            if self.serial:
                kwargs["serial_number"] = self.serial
            dev = usb.core.find(**kwargs)
            if dev is None:
                self.status.message = "Device not found"
                return False
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
            dev.set_configuration()
            self._device = dev
            self.status.connected = True
            self.status.message = "Connected"
            return True
        except Exception as e:
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
        self.status.busy = False
        self.status.message = "Disconnected"

    @property
    def is_connected(self) -> bool:
        return self.status.connected

    # ------------------------------------------------------------------
    # Low-level packet I/O
    # ------------------------------------------------------------------

    def _send_packet(self, data: bytes) -> int:
        """Send a 30-byte packet and return the status byte."""
        if not USB_AVAILABLE or self._device is None:
            return STATUS_OK
        packet = bytearray(PACKET_SIZE)
        packet[0] = 0
        for i, b in enumerate(data[:PACKET_SIZE - 2]):
            packet[i + 1] = b
        crc = self._crc(packet[1:PACKET_SIZE - 1])
        packet[PACKET_SIZE - 1] = crc
        with self._lock:
            self._device.write(ENDPOINT_WRITE, bytes(packet), timeout=5000)
            resp = self._device.read(ENDPOINT_READ, PACKET_SIZE, timeout=5000)
        return resp[1] if len(resp) > 1 else 0

    @staticmethod
    def _crc(data: bytes) -> int:
        crc = 0
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1
        return crc & 0xFF

    # ------------------------------------------------------------------
    # Machine control commands (Lhymicro-GL)
    # ------------------------------------------------------------------

    def unlock_rail(self):
        self._send_packet(b"I\x00")

    def home(self):
        self._send_packet(b"IPP\x00")

    def abort(self):
        self._abort = True
        self._send_packet(b"I\x00")

    # ------------------------------------------------------------------
    # Send raw EGV byte stream (produced by egv_writer)
    # ------------------------------------------------------------------

    def send_file_raw(
        self,
        egv_data: bytes,
        on_progress: Optional[Callable[[float], None]] = None,
        on_done:     Optional[Callable[[bool, str], None]] = None,
    ):
        """Send pre-built EGV bytes to the laser in a background thread."""
        t = threading.Thread(
            target=self._send_raw_worker,
            args=(egv_data, on_progress, on_done),
            daemon=True
        )
        t.start()

    def _send_raw_worker(self, egv_data: bytes, on_progress, on_done):
        self._abort = False
        self.status.busy = True
        self.status.progress = 0.0
        total = len(egv_data)
        chunk = PACKET_SIZE - 2
        sent  = 0

        try:
            while sent < total and not self._abort:
                piece  = egv_data[sent: sent + chunk]
                status = self._send_packet(piece)
                if status == STATUS_CRC_ERR:
                    status = self._send_packet(piece)   # retry once
                if status not in (STATUS_OK, STATUS_COMPLETE):
                    raise RuntimeError(f"Laser error status {status}")
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

    # ------------------------------------------------------------------
    # File sending
    # ------------------------------------------------------------------

    def send_file(
        self,
        file_path: str,
        on_progress: Optional[Callable[[float], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ):
        """Send an SVG/DXF file to the laser in a background thread."""
        t = threading.Thread(
            target=self._send_file_worker,
            args=(file_path, on_progress, on_done),
            daemon=True
        )
        t.start()

    def _send_file_worker(self, file_path: str, on_progress, on_done):
        self._abort = False
        self.status.busy = True
        self.status.progress = 0.0
        try:
            egv_data = self._convert_to_egv(file_path)
            total = len(egv_data)
            chunk = PACKET_SIZE - 2
            sent = 0
            while sent < total and not self._abort:
                piece = egv_data[sent: sent + chunk]
                status = self._send_packet(piece)
                if status == STATUS_CRC_ERR:
                    # retry once
                    status = self._send_packet(piece)
                if status not in (STATUS_OK, STATUS_COMPLETE):
                    raise RuntimeError(f"Laser returned error status {status}")
                sent += len(piece)
                self.status.progress = sent / total * 100
                if on_progress:
                    on_progress(self.status.progress)
                time.sleep(0.001)
            success = not self._abort
            msg = "Completed" if success else "Cancelled"
            if on_done:
                on_done(success, msg)
        except Exception as e:
            if on_done:
                on_done(False, str(e))
        finally:
            self.status.busy = False
            self.status.progress = 0.0

    def _convert_to_egv(self, file_path: str) -> bytes:
        """Convert SVG/DXF to EGV byte stream (Lhymicro-GL format).
        Currently returns a minimal home + unlock sequence as a placeholder.
        Full path generation requires vector parsing — see svg_to_egv module.
        """
        ext = file_path.lower().rsplit(".", 1)[-1]
        # Minimal EGV: home, unlock, execute
        return b"IPP\x00"


# ------------------------------------------------------------------
# Multi-machine manager
# ------------------------------------------------------------------

class MachineManager:
    """Manages up to N laser machines connected via USB."""

    def __init__(self):
        self._drivers: dict[int, K40Driver] = {}   # machine_id -> driver

    def get_driver(self, machine_id: int, vendor_id: int = K40_VENDOR_ID,
                   product_id: int = K40_PRODUCT_ID, serial: str = "") -> K40Driver:
        if machine_id not in self._drivers:
            self._drivers[machine_id] = K40Driver(vendor_id, product_id, serial)
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
            drv.send_file(file_path, **kwargs)
        else:
            raise RuntimeError(f"Machine {machine_id} is not connected")


# Global singleton
machine_manager = MachineManager()
