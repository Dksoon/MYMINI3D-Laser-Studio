"""Quick test: try different packet formats to find which one the K40 responds to."""
import sys, os, time

dll = r"C:\Program Files\K40 Whisperer\libusb0.dll"
import usb.core, usb.backend.libusb0 as _lib0
backend = _lib0.get_backend(find_library=lambda _: dll)
dev = usb.core.find(idVendor=0x1A86, idProduct=0x5512, backend=backend)
if not dev:
    print("K40 NOT FOUND"); sys.exit(1)
dev.set_configuration()
try: dev.ctrl_transfer(0x40, 177, 0x0102, 0, 0, 2000)
except: pass

def crc_onewire(data):
    c = 0
    for byte in data:
        for _ in range(8):
            mix = (c ^ byte) & 1
            c >>= 1
            if mix: c ^= 0x8C
            byte >>= 1
    return c & 0xFF

def crc_orig(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0x8408 if c & 1 else c >> 1
    return c & 0xFF

def try_packet(desc, data, timeout_r=800):
    print(f"\n[{len(data)} bytes] {desc}")
    print(f"  hex: {bytes(data).hex()}")
    try:
        dev.write(0x02, bytes(data), 500)
        resp = dev.read(0x82, 168, timeout_r)
        print(f"  RESPONSE: status={resp[1]}  bytes={list(resp[:8])}")
        return resp[1]
    except Exception as e:
        print(f"  FAIL: {e}")
        return -1

# Say hello first
print("=== Hello ===")
dev.write(0x02, bytes([0xA0]), 200)
resp = dev.read(0x82, 168, 500)
print(f"Status: {resp[1]}, bytes: {list(resp[:8])}")
time.sleep(0.3)

# ── Format A: 30-byte [0x00, I×1, 0x00×28, CRC_onewire] ──────────────
p = [0x00, 0x49] + [0x00]*27
p.append(crc_onewire(bytes(p[1:])))
try_packet("30-byte, zero-pad, OneWire CRC", p); time.sleep(0.3)

# ── Format B: 30-byte [0x00, I×1, 0x46×28, CRC_onewire] ──────────────
p = [0x00, 0x49] + [0x46]*27
p.append(crc_onewire(bytes(p[1:])))
try_packet("30-byte, F-pad, OneWire CRC", p); time.sleep(0.3)

# ── Format C: 32-byte [0xA6, 0x00, I, 0x46×27, 0xA6, CRC] ───────────
p = [0xA6, 0x00, 0x49] + [0x46]*27 + [0xA6]
p.append(crc_onewire(bytes(p[1:])))
try_packet("32-byte, A6 header+trailer, F-pad, OneWire CRC", p); time.sleep(0.3)

# ── Format D: 30-byte original [0x00, I, 0x00×28, CRC_0x8408] ─────────
p = [0x00, 0x49] + [0x00]*27
p.append(crc_orig(bytes(p[1:])))
try_packet("30-byte, zero-pad, original CRC (0x8408)", p); time.sleep(0.3)

# ── Format E: 32-byte [0x00, I, 0x46×29, CRC_onewire] ────────────────
p = [0x00, 0x49] + [0x46]*29
p.append(crc_onewire(bytes(p[1:])))
try_packet("32-byte, zero-header, F-pad, OneWire CRC", p); time.sleep(0.3)

# ── Format F: just "I" as raw byte ────────────────────────────────────
try_packet("1-byte raw I", [0x49]); time.sleep(0.3)

print("\n=== Done ===")
input("Press Enter...")
