"""config.toml loading. Missing keys fall back to config.example.toml."""
import copy
import os
import re
import shutil
import tomllib
from pathlib import Path

from . import ROOT

EXAMPLE = ROOT / "config.example.toml"
DEFAULT = ROOT / "config.toml"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def ensure(path: Path = DEFAULT) -> Path:
    """Create config.toml from the example on first use (mode 600, it may hold a token)."""
    path = Path(path)
    if not path.exists():
        shutil.copyfile(EXAMPLE, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def load(path: Path = DEFAULT) -> dict:
    with open(EXAMPLE, "rb") as f:
        cfg = tomllib.load(f)
    path = Path(path)
    if path.exists():
        with open(path, "rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
    validate(cfg)
    cfg["aliases"] = {int(k): str(v) for k, v in cfg.get("aliases", {}).items()}
    return cfg


def validate(cfg: dict):
    s = cfg["screen"]
    if s["orientation"] not in ("portrait", "landscape"):
        raise ValueError("screen.orientation must be 'portrait' or 'landscape'")
    if not 1 <= float(s["refresh"]) <= 300:
        raise ValueError("screen.refresh must be 1-300 seconds")
    for k in ("start", "end"):
        if not re.fullmatch(r"\d{1,2}:\d{2}", cfg["night"][k]):
            raise ValueError(f"night.{k} must look like 23:00")
    for k, v in cfg["thresholds"].items():
        if len(v) != 2 or v[0] > v[1]:
            raise ValueError(f"thresholds.{k} must be [warn, critical]")


def set_values(path: Path, section: str, values: dict):
    """Rewrite `key = ...` lines inside one [section], keeping comments and layout."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    current, done = None, set()
    for i, line in enumerate(lines):
        m = re.match(r"\s*\[([^\]]+)\]", line)
        if m:
            current = m.group(1).strip()
            continue
        if current != section:
            continue
        for key, val in values.items():
            m = re.match(rf"(\s*{re.escape(key)}\s*=\s*)(\"[^\"]*\"|[^#\s]+)(.*)", line, re.S)
            if m:
                lines[i] = m.group(1) + _toml(val) + m.group(3)
                done.add(key)
    missing = set(values) - done
    if missing:
        raise KeyError(f"[{section}] has no line for: {', '.join(sorted(missing))}")
    Path(path).write_text("".join(lines), encoding="utf-8")


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
