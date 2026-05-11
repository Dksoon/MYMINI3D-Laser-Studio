"""
K40 USB Diagnostic Tool
Run this on the PC connected to the K40 machine.
It will show exactly what the machine responds to each command.
"""
import sys, os, time

def main():
    print("=" * 50)
    print("  K40 USB Diagnostic Tool")
    print("=" * 50)
    print()

    # Find libusb0.dll
    exe_dir  = os.path.dirname(os.path.abspath(sys.executable))
    mei_dir  = getattr(sys, "_MEIPASS", "")
    dll_path = None
    for d in [exe_dir, mei_dir,
              r"C:\Program Files\K40 Whisperer",
              r"C:\Program Files\K40 Whisperer\driver\amd64"]:
        if not d: continue
        p = os.path.join(d, "libusb0.dll")
        if os.path.isfile(p):
            dll_path = p
            break

    if not dll_path:
        print("[FAIL] libusb0.dll not found.")
        print("       Install K40 Whisperer first, then try again.")
        input("\nPress Enter to close...")
        sys.exit(1)

    print(f"[OK]  libusb0.dll: {dll_path}")

    try:
        import usb.core
        import usb.backend.libusb0 as _lib0
        backend = _lib0.get_backend(find_library=lambda _: dll_path)
        if not backend:
            raise RuntimeError("backend is None")
        print("[OK]  USB backend loaded")
    except Exception as e:
        print(f"[FAIL] USB backend: {e}")
        input("\nPress Enter to close...")
        sys.exit(1)

    # Find K40
    print()
    print("Searching for K40 (VID=0x1A86, PID=0x5512)...")
    dev = usb.core.find(idVendor=0x1A86, idProduct=0x5512, backend=backend)
    if dev is None:
        print("[FAIL] K40 NOT FOUND on USB.")
        print("       - Check the USB cable is plugged in")
        print("       - Check the K40 machine is switched ON")
        print("       - Try Install Driver from K40 Whisperer first")
        input("\nPress Enter to close...")
        sys.exit(1)
    print(f"[OK]  K40 found: {dev}")

    # Setup
    try:
        dev.set_configuration()
        print("[OK]  set_configuration")
    except Exception as e:
        print(f"[WARN] set_configuration: {e}")

    try:
        dev.ctrl_transfer(0x40, 177, 0x0102, 0, 0, 2000)
        print("[OK]  CH341 ctrl_transfer")
    except Exception as e:
        print(f"[WARN] ctrl_transfer: {e}")

    # CRC + packet helpers
    def crc(data):
        c = 0
        for byte in data:
            for _ in range(8):
                mix = (c ^ byte) & 1
                c >>= 1
                if mix: c ^= 0x8C
                byte >>= 1
        return c & 0xFF

    def packet(cmd):
        p = bytearray(34)
        p[0] = 0xA6; p[1] = 0x00
        for i in range(30): p[2+i] = 0x46
        for i, b in enumerate(cmd[:30]): p[2+i] = b
        p[32] = 0xA6; p[33] = crc(bytes(p[1:33]))
        return bytes(p)

    def send(label, cmd_bytes, is_hello=False):
        print(f"\n--- {label} ---")
        try:
            if is_hello:
                dev.write(0x02, bytes([0xA0]), 500)
            else:
                pkt = packet(cmd_bytes)
                print(f"Packet hex: {pkt.hex()}")
                dev.write(0x02, pkt, 500)
            resp = dev.read(0x82, 168, 2000)
            s = resp[1] if len(resp) > 1 else -1
            label_map = {206: "OK/Ready", 238: "BUSY", 207: "CRC Error",
                         236: "Job Complete", 239: "Unknown"}
            meaning = label_map.get(s, "Unknown")
            print(f"Response status: {s} = {meaning}")
            print(f"Response bytes:  {list(resp[:10])}")
            return s
        except Exception as e:
            print(f"[FAIL] {e}")
            return -1

    # Tests
    send("Hello (status query)", b"", is_hello=True)
    time.sleep(0.2)

    s = send("I  — Initialize/Stop", b"I")
    time.sleep(0.3)

    print()
    print(">>> Sending IPP (go to home / top-right corner) <<<")
    print("    Watch the machine — it should start moving NOW")
    s = send("IPP — Go Home", b"IPP")
    time.sleep(1.0)

    send("IS2P — Unlock Rail", b"IS2P")

    print()
    print("=" * 50)
    print("  Diagnostic complete.")
    print("  Please take a photo/screenshot of this window")
    print("  and send it to your developer.")
    print("=" * 50)
    input("\nPress Enter to close...")

if __name__ == "__main__":
    main()
