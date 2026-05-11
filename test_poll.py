"""
Test: send command WITHOUT reading response, then poll status with hello.
K40 might not respond to commands directly -- you poll separately.
"""
import sys, os, time

dll = r"C:\Program Files\K40 Whisperer\libusb0.dll"
import usb.core, usb.backend.libusb0 as _lib0
backend = _lib0.get_backend(find_library=lambda _: dll)
dev = usb.core.find(idVendor=0x1A86, idProduct=0x5512, backend=backend)
if not dev: print("NOT FOUND"); sys.exit(1)
dev.set_configuration()
try: dev.ctrl_transfer(0x40, 177, 0x0102, 0, 0, 2000)
except: pass
print("Connected OK")

def hello():
    try:
        dev.write(0x02, bytes([0xA0]), 200)
        r = dev.read(0x82, 168, 500)
        return r[1] if len(r) > 1 else -1
    except Exception as e:
        return -1

def crc(data):
    c = 0
    for byte in data:
        for _ in range(8):
            mix = (c ^ byte) & 1
            c >>= 1
            if mix: c ^= 0x8C
            byte >>= 1
    return c & 0xFF

def make_pkt(cmd):
    p = bytearray(34)
    p[0]=0xA6; p[1]=0x00
    for i in range(30): p[2+i]=0x46
    for i,b in enumerate(cmd[:30]): p[2+i]=b
    p[32]=0xA6; p[33]=crc(bytes(p[1:33]))
    return bytes(p)

# Initial status
s = hello()
print(f"\nInitial status: {s}")
time.sleep(0.2)

# Send I command, NO read
print("\nSending I (stop) -- no read after...")
dev.write(0x02, make_pkt(b"I"), 500)
time.sleep(0.1)
s = hello()
print(f"Status after I: {s}  (206=OK, 207=CRC_ERR, 238=BUSY)")

time.sleep(0.2)

# Send IPP command, NO read, then watch
print("\nSending IPP (home) -- no read -- watch machine...")
dev.write(0x02, make_pkt(b"IPP"), 500)
print("IPP sent. Polling status for 5 seconds...")
for i in range(10):
    time.sleep(0.5)
    s = hello()
    print(f"  t={i*0.5:.1f}s  status={s}")
    if s == 206:
        print("  Machine says OK")
    elif s == 238:
        print("  Machine says BUSY (moving!)")

# Also try IS2P
time.sleep(0.3)
print("\nSending IS2P (unlock rail) -- no read...")
dev.write(0x02, make_pkt(b"IS2P"), 500)
for i in range(4):
    time.sleep(0.5)
    s = hello()
    print(f"  t={i*0.5:.1f}s  status={s}")

print("\nDone.")
