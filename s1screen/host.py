"""Local host sensors: CPU, memory, CPU temperature, package power (RAPL), NIC speed."""
import time
from dataclasses import dataclass

import psutil

RAPL = "/sys/class/powercap/intel-rapl:0"


@dataclass
class HostStats:
    name: str
    cpu: float
    mem: float
    temp: float | None
    power: float | None     # watts
    rx: float | None        # bytes/s
    tx: float | None
    uptime: float


def _read_int(path):
    try:
        with open(path) as f:
            return int(f.read())
    except (OSError, ValueError):
        return None


def cpu_temp():
    try:
        sensors = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    for chip, label in (("coretemp", "Package id 0"), ("k10temp", "Tctl"), ("zenpower", "Tdie")):
        for e in sensors.get(chip, []):
            if e.label == label:
                return e.current
    temps = [e.current for es in sensors.values() for e in es if e.current]
    return max(temps) if temps else None


class HostMonitor:
    def __init__(self, iface: str):
        import socket
        self.name = socket.gethostname()
        self.iface = iface
        self._energy = None   # (uj, t)
        self._net = None      # (rx, tx, t)
        self._rapl_max = _read_int(f"{RAPL}/max_energy_range_uj")
        psutil.cpu_percent(None)  # prime the counter

    def _power(self, now):
        uj = _read_int(f"{RAPL}/energy_uj")
        if uj is None:
            return None
        prev, self._energy = self._energy, (uj, now)
        if not prev or now <= prev[1]:
            return None
        delta = uj - prev[0]
        if delta < 0 and self._rapl_max:
            delta += self._rapl_max
        return delta / 1e6 / (now - prev[1])

    def _netspeed(self, now):
        c = psutil.net_io_counters(pernic=True).get(self.iface)
        if c is None:
            return None, None
        prev, self._net = self._net, (c.bytes_recv, c.bytes_sent, now)
        if not prev or now <= prev[2]:
            return None, None
        dt = now - prev[2]
        return max(0, c.bytes_recv - prev[0]) / dt, max(0, c.bytes_sent - prev[1]) / dt

    def sample(self) -> HostStats:
        now = time.monotonic()
        rx, tx = self._netspeed(now)
        return HostStats(
            name=self.name,
            cpu=psutil.cpu_percent(None) / 100,
            mem=psutil.virtual_memory().percent / 100,
            temp=cpu_temp(),
            power=self._power(now),
            rx=rx, tx=tx,
            uptime=time.time() - psutil.boot_time(),
        )
