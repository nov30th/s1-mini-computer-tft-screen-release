"""Background connectivity checks (e.g. Google / Apple), optionally through a SOCKS5 proxy."""
import logging
import threading
import time

import requests

log = logging.getLogger(__name__)


def check(target: dict, proxy: str) -> bool:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.get(target["url"], timeout=5, proxies=proxies, allow_redirects=False)
        return r.status_code == int(target.get("status", 200))
    except Exception as e:  # noqa: BLE001
        log.debug("%s failed: %s", target["name"], e)
        return False


class Prober(threading.Thread):
    def __init__(self, cfg: dict):
        super().__init__(daemon=True, name="probe")
        p = cfg["probe"]
        self.targets, self.proxy, self.interval = p["targets"], p.get("proxy", ""), max(5, p["interval"])
        self.results = {t["name"]: None for t in self.targets}   # None = not checked yet
        self.paused = threading.Event()

    def run(self):
        while True:
            if not self.paused.is_set():
                for t in self.targets:
                    ok = check(t, self.proxy)
                    if self.results.get(t["name"]) is not False and not ok:
                        log.info("probe %s: unreachable", t["name"])
                    self.results[t["name"]] = ok
            time.sleep(self.interval)
