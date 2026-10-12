"""Proxmox VE API: one /cluster/resources call per refresh."""
import logging
import time
from dataclasses import dataclass, field

import requests
import urllib3

log = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ONBOOT_TTL = 300  # seconds to cache a stopped guest's onboot flag


@dataclass
class Guest:
    vmid: int
    name: str
    kind: str            # qemu | lxc
    running: bool
    cpu: float = 0.0     # fraction of its own vCPUs
    mem: float = 0.0     # fraction of its maxmem
    net: float = 0.0     # bytes/s in+out
    alert: bool = False  # onboot=1 but not running


@dataclass
class Snapshot:
    guests: list = field(default_factory=list)
    storage: dict = field(default_factory=dict)   # name -> used fraction
    error: str = ""


class PveClient:
    def __init__(self, cfg: dict):
        p = cfg["pve"]
        self.base = f"https://{p['host']}:{p['port']}/api2/json"
        self.ignore = {int(v) for v in p.get("ignore", [])}
        self.user, self.password = p.get("user", ""), p.get("password", "")
        self.s = requests.Session()
        self.s.verify = bool(p.get("verify_ssl", False))
        self.token = bool(p.get("token_id") and p.get("token_secret"))
        if self.token:
            self.s.headers["Authorization"] = f"PVEAPIToken={p['token_id']}={p['token_secret']}"
        self._logged_in = False
        self._prev_net = {}       # vmid -> (bytes, t)
        self._onboot = {}         # vmid -> (flag, t)

    def _login(self):
        if not self.password:
            raise RuntimeError("no token or password in [pve]")
        r = self.s.post(f"{self.base}/access/ticket", timeout=8,
                        data={"username": self.user, "password": self.password})
        r.raise_for_status()
        self.s.cookies.set("PVEAuthCookie", r.json()["data"]["ticket"])
        self._logged_in = True

    def get(self, path: str):
        if not self.token and not self._logged_in:
            self._login()
        r = self.s.get(self.base + path, timeout=8)
        if r.status_code == 401 and not self.token:   # ticket expired (2h)
            self._login()
            r = self.s.get(self.base + path, timeout=8)
        if r.status_code == 401:
            raise RuntimeError("401 unauthorized - check token/password")
        r.raise_for_status()
        return r.json()["data"]

    def _is_onboot(self, r: dict) -> bool:
        vmid, now = r["vmid"], time.time()
        hit = self._onboot.get(vmid)
        if hit and now - hit[1] < ONBOOT_TTL:
            return hit[0]
        try:
            conf = self.get(f"/nodes/{r['node']}/{r['type']}/{vmid}/config")
            flag = bool(int(conf.get("onboot", 0)))
        except Exception:  # noqa: BLE001 - treat unknown as "not expected to run"
            flag = False
        self._onboot[vmid] = (flag, now)
        return flag

    def snapshot(self) -> Snapshot:
        snap = Snapshot()
        now = time.time()
        for r in self.get("/cluster/resources"):
            t = r.get("type")
            if t == "storage" and r.get("maxdisk"):
                snap.storage[r["storage"]] = r.get("disk", 0) / r["maxdisk"]
            if t not in ("qemu", "lxc") or r.get("template") or r["vmid"] in self.ignore:
                continue
            running = r.get("status") == "running"
            g = Guest(vmid=r["vmid"], name=r.get("name") or str(r["vmid"]), kind=t, running=running)
            if running:
                g.cpu = float(r.get("cpu", 0))
                g.mem = r.get("mem", 0) / r["maxmem"] if r.get("maxmem") else 0.0
                total = r.get("netin", 0) + r.get("netout", 0)
                prev = self._prev_net.get(g.vmid)
                if prev and total >= prev[0] and now > prev[1]:
                    g.net = (total - prev[0]) / (now - prev[1])
                self._prev_net[g.vmid] = (total, now)
            elif self._is_onboot(r):
                g.alert = True
            else:
                continue                      # stopped on purpose: not shown
            snap.guests.append(g)
        snap.guests.sort(key=lambda g: g.vmid)
        return snap
