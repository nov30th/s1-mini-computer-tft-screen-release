"""Main loop: collect -> evaluate -> render -> send. Heartbeat runs on its own thread."""
import logging
import time
from datetime import datetime, time as dtime

from .host import HostMonitor
from .lcd import Lcd
from .led import Led
from .probe import Prober
from .pve import PveClient, Snapshot
from .render import Frame, Renderer, black

log = logging.getLogger(__name__)


def _hm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def in_window(now: dtime, start: str, end: str) -> bool:
    a, b = _hm(start), _hm(end)
    if a == b:
        return False
    return a <= now < b if a < b else now >= a or now < b


def evaluate(cfg: dict, host, snap: Snapshot, probes: dict) -> int:
    """0 normal, 1 warn, 2 error -> picks the background and the LED preset."""
    th = cfg["thresholds"]
    values = [(host.cpu, th["cpu"]), (host.mem, th["mem"]), (host.temp, th["temp"])]
    values += [(v, th["storage"]) for v in snap.storage.values()]
    values += [(g.cpu, th["guest_cpu"]) for g in snap.guests if g.running]
    level = 0
    for v, (warn, crit) in values:
        if v is None:
            continue
        if v >= crit:
            return 2
        if v >= warn:
            level = 1
    if snap.error or any(g.alert for g in snap.guests):   # probes only colour their own dots
        level = max(level, 1)
    return level


class Collector:
    """Gathers host + PVE + probe data into a Frame. Used by the service and by `preview`."""

    def __init__(self, cfg: dict, prober=None):
        self.cfg = cfg
        self.pve = PveClient(cfg)
        self.host = HostMonitor(cfg["screen"]["net_iface"])
        self.prober = prober
        self._last_error = None

    def _snapshot(self) -> Snapshot:
        try:
            snap = self.pve.snapshot()
            if self._last_error:
                log.info("PVE API back to normal")
            self._last_error = None
            return snap
        except Exception as e:  # noqa: BLE001 - keep drawing host stats when the API is down
            msg = str(e).split("(Caused by")[0].strip()
            if msg != self._last_error:
                log.error("PVE API: %s", msg)
            self._last_error = msg
            return Snapshot(error=msg)

    def frame(self, probes=None):
        host = self.host.sample()
        snap = self._snapshot()
        if probes is None:
            probes = dict(self.prober.results) if self.prober else {}
        return Frame(host, snap, probes, evaluate(self.cfg, host, snap, probes))


class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.lcd = Lcd()
        self.led = Led(cfg["led"]["port"]) if cfg["led"]["enabled"] else None
        self.renderer = Renderer(cfg)
        self.prober = Prober(cfg) if cfg["probe"]["enabled"] else None
        self.collector = Collector(cfg, self.prober)

    def _draw(self, img):
        try:
            self.lcd.draw(img)
            self._draw_errors = 0
        except OSError as e:
            self._draw_errors = getattr(self, "_draw_errors", 0) + 1
            log.warning("frame write failed (%d in a row): %s", self._draw_errors, e)
            if self._draw_errors >= 10:   # let systemd restart us with a fresh handle
                raise

    def run(self):
        self.lcd.open()
        if self.prober:
            self.prober.start()
        night_cfg, led_cfg = self.cfg["night"], self.cfg["led"]
        refresh = float(self.cfg["screen"]["refresh"])
        was_night = None
        while True:
            started = time.monotonic()
            night = night_cfg["enabled"] and in_window(datetime.now().time(), night_cfg["start"], night_cfg["end"])
            if night:
                self._draw(black())                 # resent every cycle, like the original program
                if was_night is not True:
                    log.info("night mode on")
                    if self.led:
                        self.led.apply(led_cfg["night"])
                    if self.prober:
                        self.prober.paused.set()
            else:
                if was_night:
                    log.info("night mode off")
                    if self.prober:
                        self.prober.paused.clear()
                f = self.collector.frame()
                _, device_img = self.renderer.render(f)
                self._draw(device_img)
                if self.led:
                    self.led.apply(led_cfg[("normal", "warn", "error")[f.level]])
            was_night = night
            time.sleep(max(0.5, refresh - (time.monotonic() - started)))
