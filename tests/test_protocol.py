import unittest
from datetime import time as dtime

from s1screen import lcd
from s1screen.app import in_window
from s1screen.render import short_name, fmt_rate


def legacy_frame_packets(image_bytes: bytes):
    """Packet builder from the original core.py (2024), kept as the reference."""
    out = []
    for x in range(0, 26):
        hex_data = f"55 A3 F{'0' if x == 0 else '1'} {x + 1:02x} 00 {x % 16:x}0 00 10"
        pkt = bytes.fromhex(hex_data.replace(" ", "")) + image_bytes[:4096]
        image_bytes = image_bytes[4096:]
        out.append(pkt.ljust(4104, b"\x00"))
    pkt = bytes.fromhex("55A3F21B00A00009") + image_bytes
    out.append(pkt.ljust(4104, b"\x00"))
    return out


class FramePackets(unittest.TestCase):
    def test_matches_legacy_builder(self):
        data = bytes(range(256)) * (lcd.FRAME_BYTES // 256) + bytes(lcd.FRAME_BYTES % 256)
        self.assertEqual(len(data), 320 * 170 * 2)
        self.assertEqual(lcd.frame_packets(data), legacy_frame_packets(data))

    def test_rgb565_big_endian(self):
        from PIL import Image
        img = Image.new("RGB", (320, 170), (255, 0, 0))
        img.putpixel((1, 0), (0, 255, 0))
        img.putpixel((2, 0), (0, 0, 255))
        raw = lcd.rgb565(img)
        self.assertEqual(raw[0:6], bytes.fromhex("F800" "07E0" "001F"))


class NightWindow(unittest.TestCase):
    def test_wraps_midnight(self):
        self.assertTrue(in_window(dtime(23, 30), "23:00", "07:00"))
        self.assertTrue(in_window(dtime(6, 59), "23:00", "07:00"))
        self.assertFalse(in_window(dtime(7, 0), "23:00", "07:00"))
        self.assertFalse(in_window(dtime(12, 0), "23:00", "07:00"))

    def test_same_day(self):
        self.assertTrue(in_window(dtime(13, 0), "12:30", "14:00"))
        self.assertFalse(in_window(dtime(14, 0), "12:30", "14:00"))

    def test_empty(self):
        self.assertFalse(in_window(dtime(1, 0), "00:00", "00:00"))


class Formatting(unittest.TestCase):
    def test_short_name_keeps_tail(self):
        self.assertEqual(short_name("openwrt254", 9), "openw…254")
        self.assertEqual(short_name("openwrt251", 9), "openw…251")
        self.assertEqual(short_name("haos", 9), "haos")

    def test_rate(self):
        self.assertEqual(fmt_rate(0), "0k")
        self.assertEqual(fmt_rate(12 * 1024), "12k")
        self.assertEqual(fmt_rate(1.3 * 1024 * 1024), "1.3m")
        self.assertEqual(fmt_rate(25 * 1024 * 1024), "25m")
        self.assertEqual(fmt_rate(None), "-")


if __name__ == "__main__":
    unittest.main()
