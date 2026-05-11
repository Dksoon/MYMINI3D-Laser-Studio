"""
K40 USB diagnostic — run this to see exactly what the machine responds.
Usage:  python test_k40.py
"""
import sys, os, time

# ── Load libusb0 from K40 Whisperer ──────────────────────────────────
K40W_DIR = r"C:\Program Files\K40 Whisperer"
dll_path  = os.path.join(K40W_DIR, "libusb0.dll")

if not os.path.exists(dll_path):
    print(f"ERROR: {dll_path} not found")
    sys.exit(1)

try:
    import usb.core
    import usb.backend.libusb0 as _lib0
    backend = _lib0.get_backend(find_library=lambda _: dll_path)
    if backend is None:
        raise RuntimeError("libusb0 backend returned None")
    print(f"[OK] libusb0 backend loaded from {dll_path}")
except Exception as e:
    print(f"[FAIL] USB backend: {e}")
    sys.exit(1)

# ── Find K40 ──────────────────────────────────────────────────────────
print("\nSearching for K40 (VID=0x1A86 PID=0x5512)...")
dev = usb.core.find(idVendor=0x1A86, idProduct=0x5512, backend=backend)
if dev is None:
    print("[FAIL] K40 not found on USB. Check cable and driver.")
    sys.exit(1)
print(f"[OK] K40 found: {dev}")

# ── Setup ─────────────────────────────────────────────────────────────
try:
    dev.set_configuration()
    print("[OK] set_configuration")
except Exception as e:
    print(f"[WARN] set_configuration: {e}")

try:
    dev.ctrl_transfer(0x40, 177, 0x0102, 0, 0, 2000)
    print("[OK] ctrl_transfer (CH341 init)")
except Exception as e:
    print(f"[WARN] ctrl_transfer: {e}")

# ── CRC helper ────────────────────────────────────────────────────────
def k40_crc(data):
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 1
            crc >>= 1
            if mix: crc ^= 0x8C
            byte >>= 1
    return crc & 0xFF

# ── Packet builder ────────────────────────────────────────────────────
def make_packet(cmd_bytes):
    p = bytearray(34)
    p[0] = 0xA6; p[1] = 0x00
    for i in range(30): p[2+i] = 0x46
    for i, b in enumerate(cmd_bytes[:30]): p[2+i] = b
    p[32] = 0xA6
    p[33] = k40_crc(bytes(p[1:33]))
    return bytes(p)

# ── Say hello ─────────────────────────────────────────────────────────
print("\n--- Say hello [0xA0] ---")
try:
    dev.write(0x02, bytes([0xA0]), 200)
    resp = dev.read(0x82, 168, 500)
    print(f"Response bytes 0-9: {list(resp[:10])}")
    print(f"Status byte [1]:    {resp[1]}  (OK=206, BUSY=238, CRC_ERR=207)")
except Exception as e:
    print(f"[FAIL] hello: {e}")

time.sleep(0.1)

# ── Send I (initialize/stop) ──────────────────────────────────────────
print("\n--- Send  I  (Initialize/Stop) ---")
pkt = make_packet(b"I")
print(f"Packet: {list(pkt)}")
try:
    dev.write(0x02, pkt, 200)
    resp = dev.read(0x82, 168, 500)
    print(f"Response bytes 0-9: {list(resp[:10])}")
    print(f"Status byte [1]:    {resp[1]}")
except Exception as e:
    print(f"[FAIL] I: {e}")

time.sleep(0.2)

# ── Send IPP (go home) ────────────────────────────────────────────────
print("\n--- Send IPP (go home / top-right corner) ---")
pkt = make_packet(b"IPP")
print(f"Packet: {list(pkt)}")
try:
    dev.write(0x02, pkt, 200)
    resp = dev.read(0x82, 168, 1000)
    print(f"Response bytes 0-9: {list(resp[:10])}")
    print(f"Status byte [1]:    {resp[1]}")
    print("\n>>> Did the machine move? <<<")
except Exception as e:
    print(f"[FAIL] IPP: {e}")

time.sleep(0.5)

# ── Send IS2P (unlock rail) ───────────────────────────────────────────
print("\n--- Send IS2P (unlock rail) ---")
pkt = make_packet(b"IS2P")
print(f"Packet: {list(pkt)}")
try:
    dev.write(0x02, pkt, 200)
    resp = dev.read(0x82, 168, 500)
    print(f"Response bytes 0-9: {list(resp[:10])}")
    print(f"Status byte [1]:    {resp[1]}")
except Exception as e:
    print(f"[FAIL] IS2P: {e}")

print("\n--- Done ---")
