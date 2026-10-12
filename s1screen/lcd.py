"""Front TFT: USB 04d9:fd01, interface 1, 320x170 RGB565 (big-endian).

Packets are 4104 bytes (8-byte header + 4096 data). See docs/protocol.md.
After a full frame the panel is busy for ~6.5 s and NAKs everything, so one
frame takes ~9 s end to end. Writes simply block (long timeout) until it is ready.
Interface 1 only has an interrupt OUT endpoint, so the kernel's usbhid never
binds it (no /dev/hidraw). We claim it through usbfs and write to the endpoint
directly - the same thing libusb does, without needing libusb.
"""
import ctypes
import glob
import logging
import os
import struct
import threading

import numpy as np

try:
    import fcntl
except ImportError:  # Windows: preview/tests only
    fcntl = None

log = logging.getLogger(__name__)

VID, PID, INTERFACE = 0x04D9, 0xFD01, 1
WIDTH, HEIGHT = 320, 170
PACKET_SIZE = 4104
CHUNK = 4096
FRAME_BYTES = WIDTH * HEIGHT * 2
TIMEOUT_MS = 10000      # covers the ~6.5 s busy period after the previous frame


def rgb565(img) -> bytes:
    """PIL image (320x170) -> big-endian RGB565 bytes."""
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    v = ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    return v.astype(">u2").tobytes()


def frame_packets(data: bytes) -> list:
    """Split a full frame into 27 packets: 55 A3 <F0|F1|F2> <seq> <offset LE16> <len LE16> + data."""
    count = (len(data) + CHUNK - 1) // CHUNK
    packets = []
    for i in range(count):
        chunk = data[i * CHUNK:(i + 1) * CHUNK]
        kind = 0xF0 if i == 0 else 0xF2 if i == count - 1 else 0xF1
        header = bytes([0x55, 0xA3, kind, i + 1]) + struct.pack("<HH", (i * CHUNK) & 0xFFFF, len(chunk))
        packets.append((header + chunk).ljust(PACKET_SIZE, b"\x00"))
    return packets


def command_packet(*payload: int) -> bytes:
    return bytes(payload).ljust(PACKET_SIZE, b"\x00")


# ---- usbfs -----------------------------------------------------------------
class _BulkTransfer(ctypes.Structure):  # struct usbdevfs_bulktransfer
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint),
                ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("U") << 8) | nr


USBDEVFS_BULK = _ioc(3, 2, ctypes.sizeof(_BulkTransfer))
USBDEVFS_CLAIMINTERFACE = _ioc(2, 15, ctypes.sizeof(ctypes.c_uint))
USBDEVFS_RELEASEINTERFACE = _ioc(2, 16, ctypes.sizeof(ctypes.c_uint))


def _read(path):
    with open(path) as f:
        return f.read().strip()


def find_device():
    """-> (/dev/bus/usb/BBB/DDD, OUT endpoint address) or None."""
    for dev in glob.glob("/sys/bus/usb/devices/*"):
        try:
            if (int(_read(f"{dev}/idVendor"), 16), int(_read(f"{dev}/idProduct"), 16)) != (VID, PID):
                continue
            node = f"/dev/bus/usb/{int(_read(f'{dev}/busnum')):03d}/{int(_read(f'{dev}/devnum')):03d}"
        except (OSError, ValueError):
            continue
        for ep in glob.glob(f"{dev}/*:1.{INTERFACE}/ep_*"):
            if _read(f"{ep}/direction") == "out":
                return node, int(_read(f"{ep}/bEndpointAddress"), 16)
    return None


class Lcd:
    def __init__(self):
        self.fd = None
        self.ep = None
        self.lock = threading.Lock()

    def open(self):
        found = find_device()
        if not found:
            raise RuntimeError("S1 screen (USB 04d9:fd01) not found")
        node, self.ep = found
        self.fd = os.open(node, os.O_RDWR)
        try:
            fcntl.ioctl(self.fd, USBDEVFS_CLAIMINTERFACE, struct.pack("I", INTERFACE))
        except OSError as e:
            os.close(self.fd)
            self.fd = None
            raise RuntimeError(f"cannot claim the screen ({e}); is another program "
                               "(e.g. the old core.bin) still running?") from e
        log.info("screen opened at %s interface %d ep 0x%02x", node, INTERFACE, self.ep)

    def _write(self, pkt: bytes):
        buf = ctypes.create_string_buffer(pkt, len(pkt))
        xfer = _BulkTransfer(self.ep, len(pkt), TIMEOUT_MS, ctypes.cast(buf, ctypes.c_void_p))
        fcntl.ioctl(self.fd, USBDEVFS_BULK, xfer)

    def draw(self, img):
        """img: PIL image already in the native 320x170 landscape frame."""
        packets = frame_packets(rgb565(img))
        with self.lock:
            for pkt in packets:
                self._write(pkt)

    def close(self):
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, USBDEVFS_RELEASEINTERFACE, struct.pack("I", INTERFACE))
            finally:
                os.close(self.fd)
                self.fd = None
