"""Draws one frame. Portrait = 170x320 (rotated for the device), landscape = 320x170.

The top ~17px are left untouched so the text baked into the background stays visible.
Layout coordinates are in device pixels; `scale` > 1 renders the same layout at a
higher resolution (used for previews / screenshots).
"""
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import ASSETS

WHITE, DIM, CYAN = (235, 235, 235), (150, 160, 170), (90, 200, 255)
GREEN, YELLOW, RED, TRACK = (80, 220, 120), (250, 210, 60), (255, 80, 80), (70, 70, 78)
LEVEL_NAMES = ("normal", "warn", "error")
PANEL_ALPHA = 200
CHAR_W = 6.6  # JetBrains Mono at 11px


@lru_cache(maxsize=None)
def font(size: float, bold=False):
    name = "JetBrainsMono-Bold.ttf" if bold else "JetBrainsMono-Regular.ttf"
    return ImageFont.truetype(str(ASSETS / "fonts" / name), round(size))


@lru_cache(maxsize=None)
def background(orientation: str, level: int, size: tuple):
    path = ASSETS / "bg" / f"{orientation}-{LEVEL_NAMES[level]}.png"
    img = Image.open(path).convert("RGBA")
    return img if img.size == size else img.resize(size, Image.LANCZOS)


def short_name(name: str, n: int) -> str:
    return name if len(name) <= n else name[:n - 4] + "…" + name[-3:]


def fmt_rate(b) -> str:
    if b is None:
        return "-"
    if b < 1024 * 1000:
        return f"{b / 1024:.0f}k"
    m = b / 1048576
    return f"{m:.1f}m" if m < 10 else f"{m:.0f}m"


def fmt_uptime(s: float) -> str:
    if s >= 86400:
        return f"{s // 86400:.0f}d"
    return f"{s // 3600:.0f}h" if s >= 3600 else f"{s // 60:.0f}m"


def pick(v, limits, ok=GREEN):
    if v is None:
        return DIM
    return RED if v >= limits[1] else YELLOW if v >= limits[0] else ok


class Frame:
    """Everything the layouts need, decoupled from where it came from (live or demo)."""

    def __init__(self, host, snap, probes: dict, level: int):
        self.host, self.snap, self.probes, self.level = host, snap, probes, level


class Canvas:
    """ImageDraw in device-pixel coordinates, drawn at `s` times the resolution."""

    def __init__(self, orientation: str, level: int, size: tuple, s: int):
        self.s = s
        self.img = background(orientation, level, (size[0] * s, size[1] * s)).copy()
        self.d = ImageDraw.Draw(self.img)

    def _xy(self, *v):
        return [round(x * self.s) for x in v]

    def panel(self, box):
        ov = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle(self._xy(*box), 4 * self.s, fill=(0, 0, 0, PANEL_ALPHA))
        self.img = Image.alpha_composite(self.img, ov)
        self.d = ImageDraw.Draw(self.img)

    def text(self, xy, txt, size, fill, bold=False, anchor=None):
        self.d.text(self._xy(*xy), txt, font=font(size * self.s, bold), fill=fill, anchor=anchor)

    def rect(self, box, fill):
        self.d.rectangle(self._xy(*box), fill=fill)

    def dot(self, box, fill):
        self.d.ellipse(self._xy(*box), fill=fill)

    def arc(self, box, start, end, fill, width):
        self.d.arc(self._xy(*box), start, end, fill=fill, width=round(width * self.s))


class Renderer:
    def __init__(self, cfg: dict, scale: int = 1):
        self.cfg = cfg
        self.scale = scale
        self.th = cfg["thresholds"]
        self.orientation = cfg["screen"]["orientation"]
        self.aliases = cfg.get("aliases", {})
        self.ring_storage = cfg["screen"]["ring_storage"]

    # ---- widgets ---------------------------------------------------------
    @staticmethod
    def _bar(c, x, y, w, v, color, h=4):
        c.rect((x, y, x + w, y + h), TRACK)
        if v and v > 0:
            c.rect((x, y, x + max(1, w * min(v, 1)), y + h), color)

    @staticmethod
    def _ring(c, cx, cy, r, frac, color, value: str, label: str):
        box = (cx - r, cy - r, cx + r, cy + r)
        c.arc(box, 135, 405, TRACK, 5)
        if frac and frac > 0:
            c.arc(box, 135, 135 + 270 * min(frac, 1), color, 5)
        c.text((cx, cy - 1), value, 12, WHITE, bold=True, anchor="mm")
        c.text((cx, cy + r - 3), label, 9, DIM, anchor="mm")

    def _rings(self, c, f: Frame, centers, r):
        h, th = f.host, self.th
        st = f.snap.storage.get(self.ring_storage)
        items = [
            (h.cpu, pick(h.cpu, th["cpu"]), f"{h.cpu * 100:.0f}", "CPU"),
            (h.mem, pick(h.mem, th["mem"]), f"{h.mem * 100:.0f}", "MEM"),
            ((h.temp or 0) / 100, pick(h.temp, th["temp"]), f"{h.temp:.0f}" if h.temp else "-", "°C"),
            (st, pick(st, th["storage"], CYAN), f"{st * 100:.0f}" if st is not None else "-",
             self.ring_storage.replace("local-", "")[:5].upper()),
        ]
        for (cx, cy), (frac, color, value, label) in zip(centers, items):
            self._ring(c, cx, cy, r, frac, color, value, label)

    def _guest_rows(self, c, guests, x0, x1, y, row_h, bar_w):
        net_x = x1 - 4
        mem_x = net_x - 30 - bar_w
        cpu_x = mem_x - 6 - bar_w
        max_chars = int((cpu_x - (x0 + 7) - 4) / CHAR_W)
        for g in guests:
            name = short_name(self.aliases.get(g.vmid, g.name), max_chars)
            c.dot((x0, y + 5, x0 + 4, y + 9), GREEN if g.running else RED)
            c.text((x0 + 7, y), name, 11, WHITE if g.running else RED)
            if g.running:
                self._bar(c, cpu_x, y + 5, bar_w, max(g.cpu, 0.02), pick(g.cpu, self.th["guest_cpu"], CYAN))
                self._bar(c, mem_x, y + 5, bar_w, g.mem, pick(g.mem, self.th["guest_mem"]))
                c.text((net_x, y), fmt_rate(g.net), 11, DIM, anchor="ra")
            else:
                c.text((net_x, y + 1), "STOPPED", 10, RED, anchor="ra")
            y += row_h

    @staticmethod
    def _error(c, x, y, msg):
        c.text((x, y), "PVE API", 11, RED, bold=True)
        for i in range(0, min(len(msg), 120), 22):
            y += 14
            c.text((x, y), msg[i:i + 22], 10, RED)

    @staticmethod
    def _probes(c, x, y, probes, short=False):
        for name, ok in probes.items():
            c.dot((x, y + 4, x + 5, y + 9), DIM if ok is None else GREEN if ok else RED)
            label = name[0] if short else name
            c.text((x + 8, y), label, 11, WHITE)
            x += 8 + round(len(label) * CHAR_W) + 7

    @staticmethod
    def _fit(guests, rows):
        """Keep alerts first, then the busiest; show them in vmid order."""
        if len(guests) <= rows:
            return guests, 0
        keep = sorted(guests, key=lambda g: (not g.alert, -g.cpu, -g.mem))[:rows]
        return sorted(keep, key=lambda g: g.vmid), len(guests) - rows

    @staticmethod
    def _count(snap):
        alerts = sum(g.alert for g in snap.guests)
        running = sum(g.running for g in snap.guests)
        return f"{running}/{running + alerts}", RED if alerts else GREEN

    # ---- layouts ---------------------------------------------------------
    def portrait(self, f: Frame):
        W, H = 170, 320
        c = Canvas("portrait", f.level, (W, H), self.scale)
        for box in ((2, 18, W - 3, 106), (2, 110, W - 3, 300), (2, 303, W - 3, H - 2)):
            c.panel(box)
        h = f.host
        c.text((6, 20), h.name, 12, CYAN, bold=True)
        c.text((W - 6, 22), f"up {fmt_uptime(h.uptime)}", 10, DIM, anchor="ra")
        self._rings(c, f, [(23, 56), (64, 56), (105, 56), (146, 56)], 18)
        power = f"{h.power:.1f}W  " if h.power else ""
        c.text((W // 2, 86), f"{power}↓{fmt_rate(h.rx)} ↑{fmt_rate(h.tx)}", 11, WHITE, anchor="ma")

        c.text((6, 112), "GUEST", 9, DIM)
        c.text((W - 6, 112), "cpu  mem   net", 9, DIM, anchor="ra")
        guests, more = self._fit(f.snap.guests, 10)
        if f.snap.error:
            self._error(c, 6, 128, f.snap.error)
        else:
            self._guest_rows(c, guests, 6, W - 2, 126, 16, 20)

        self._probes(c, 6, 304, f.probes)
        count, color = self._count(f.snap)
        if more:
            count = f"+{more} {count}"
        c.text((W - 6, 304), count, 11, color, anchor="ra")
        return c.img

    def landscape(self, f: Frame):
        W, H = 320, 170
        c = Canvas("landscape", f.level, (W, H), self.scale)
        c.panel((2, 18, 104, H - 3))
        c.panel((107, 18, W - 3, H - 3))
        h = f.host
        c.text((6, 20), h.name[:9], 12, CYAN, bold=True)
        c.text((100, 22), fmt_uptime(h.uptime), 10, DIM, anchor="ra")
        self._rings(c, f, [(28, 57), (78, 57), (28, 103), (78, 103)], 19)
        c.text((6, 127), f"{h.power:.1f}W" if h.power else "", 11, WHITE)
        c.text((100, 127), f"↓{fmt_rate(h.rx)}", 11, WHITE, anchor="ra")
        self._probes(c, 6, 149, f.probes, short=True)
        guests, more = self._fit(f.snap.guests, 10)
        count, color = self._count(f.snap)
        c.text((100, 149), f"+{more}" if more else count, 11, color, anchor="ra")
        if f.snap.error:
            self._error(c, 113, 22, f.snap.error)
        else:
            self._guest_rows(c, guests, 112, W - 2, 21, 14, 22)
        return c.img

    def render(self, f: Frame):
        """Returns (preview image as seen by a person, image in the device's native frame)."""
        if self.orientation == "portrait":
            img = self.portrait(f).convert("RGB")
            return img, img.rotate(90, expand=True)
        img = self.landscape(f).convert("RGB")
        return img, img


def black():
    return Image.new("RGB", (320, 170), (0, 0, 0))
