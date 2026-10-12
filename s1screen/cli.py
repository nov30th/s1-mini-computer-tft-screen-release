"""Command line + interactive menu. `./s1screen.py` with no arguments opens the menu."""
import argparse
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import ROOT, __version__, config

SERVICE = "s1screen"
UNIT_PATH = Path(f"/etc/systemd/system/{SERVICE}.service")
APT_DEPS = {"PIL": "python3-pil", "numpy": "python3-numpy", "psutil": "python3-psutil",
            "requests": "python3-requests", "socks": "python3-socks", "serial": "python3-serial"}
TOKEN_NAME = "s1screen"

UNIT = """[Unit]
Description=AceMagic S1 front screen (Proxmox VE status)
After=network-online.target pve-cluster.service pveproxy.service
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} {script} --config {config} run
WorkingDirectory={root}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


# ---- helpers ---------------------------------------------------------------
def sh(*cmd, check=False, capture=False):
    return subprocess.run(cmd, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def need_root():
    if os.name != "posix" or os.geteuid() != 0:
        sys.exit("Please run as root / 请用 root 运行")


def ask(prompt: str, default=False) -> bool:
    if not sys.stdin.isatty():
        return default
    ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not ans else ans in ("y", "yes")


def service_state() -> str:
    if not shutil.which("systemctl"):
        return "n/a"
    if not UNIT_PATH.exists():
        return "not installed"
    return sh("systemctl", "is-active", SERVICE, capture=True).stdout.strip()


def missing_deps():
    out = []
    for mod, pkg in APT_DEPS.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            out.append(pkg)
    return out


def legacy_units():
    """Units of the old closed-source release (core.bin) that would fight over the screen."""
    found = []
    for unit in Path("/etc/systemd/system").glob("*.service"):
        if unit.name == UNIT_PATH.name:
            continue
        try:
            text = unit.read_text(errors="ignore")
        except OSError:
            continue
        if "core.bin" in text:
            found.append(unit.name)
    return found


# ---- commands --------------------------------------------------------------
def cmd_run(args):
    from .app import App
    if sys.stdin.isatty() and service_state() == "active":
        sys.exit(f"{SERVICE}.service is running; stop it first (./s1screen.py uninstall or systemctl stop {SERVICE})")
    App(config.load(args.config)).run()


def demo_frame(cfg):
    from .host import HostStats
    from .pve import Guest, Snapshot
    from .app import evaluate
    from .render import Frame
    host = HostStats("pve", 0.23, 0.68, 56, 7.8, 1.4 * 1048576, 180 * 1024, 45 * 86400)
    g = lambda vmid, name, cpu, mem, net, kind="lxc": Guest(vmid, name, kind, True, cpu, mem, net)
    snap = Snapshot(guests=[
        g(100, "pihole", .01, .35, 12e3), g(101, "homeassistant", .06, .58, 38e3, "qemu"),
        g(102, "openwrt", .03, .41, 1.2e6, "qemu"), g(103, "docker", .22, .67, 260e3),
        g(104, "nas", .04, .52, 3.4e6, "qemu"), g(105, "jellyfin", .61, .74, 18e6),
        g(106, "win11", .12, .81, 520e3, "qemu"), g(107, "nginx-proxy", 0, .2, 96e3),
        g(108, "uptime-kuma", .01, .48, 3e3), g(109, "backup", 0, .23, 0),
    ], storage={"local": .25, "local-lvm": .42})
    probes = {t["name"]: True for t in cfg["probe"]["targets"]} if cfg["probe"]["enabled"] else {}
    return Frame(host, snap, probes, evaluate(cfg, host, snap, probes))


def cmd_preview(args):
    from .render import Renderer
    cfg = config.load(args.config)
    if args.orientation:
        cfg["screen"]["orientation"] = args.orientation
    if args.demo:
        frame = demo_frame(cfg)
    else:
        from .app import Collector
        from .probe import check
        collector = Collector(cfg)
        collector.frame(probes={})          # first sample primes the rate counters
        time.sleep(1.5)
        probes = {}
        if cfg["probe"]["enabled"]:
            probes = {t["name"]: check(t, cfg["probe"].get("proxy", "")) for t in cfg["probe"]["targets"]}
        frame = collector.frame(probes)
    img, _ = Renderer(cfg, scale=max(1, args.scale)).render(frame)
    img.save(args.output)
    print(f"saved {args.output}")


def cmd_check(args):
    from . import lcd, led
    path = Path(args.config)
    print(f"s1screen {__version__}")
    try:
        cfg = config.load(path)
        print(f"[ok]   config {path}" + ("" if path.exists() else " (missing, using example defaults)"))
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] config {path}: {e}")
        return
    deps = missing_deps()
    print("[ok]   python packages" if not deps else f"[FAIL] missing: apt install {' '.join(deps)}")
    print(f"[info] service: {service_state()}")
    for u in legacy_units():
        print(f"[warn] old release service {u} is installed (it will be disabled by `install`)")
    dev = lcd.find_device()
    print(f"[ok]   screen {dev[0]} ep 0x{dev[1]:02x}" if dev else "[FAIL] screen (USB 04d9:fd01) not found")
    if cfg["led"]["enabled"]:
        port = led.resolve_port(cfg["led"]["port"])
        print(f"[ok]   LED {port}" if port else f"[warn] LED port not found (port={cfg['led']['port']})")
    else:
        print("[info] LED disabled in config")
    for tty, usb, fixed in led.ch340_ports():
        print(f"         CH340 {tty} usb {usb} {'internal' if fixed else 'external'}")
    if deps:
        return
    from .pve import PveClient
    from .probe import check
    try:
        snap = PveClient(cfg).snapshot()
        alerts = [g.name for g in snap.guests if g.alert]
        print(f"[ok]   PVE API: {sum(g.running for g in snap.guests)} running"
              + (f", onboot but stopped: {', '.join(alerts)}" if alerts else "")
              + f"; storage: {', '.join(snap.storage)}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] PVE API: {e}")
    if cfg["probe"]["enabled"]:
        for t in cfg["probe"]["targets"]:
            print(f"[{'ok' if check(t, cfg['probe'].get('proxy', '')) else 'FAIL':4}] probe {t['name']}")


def cmd_token(args):
    need_root()
    if not shutil.which("pveum"):
        sys.exit("pveum not found - run this on the Proxmox VE host")
    path = config.ensure(args.config)
    user = args.user
    full = f"{user}!{TOKEN_NAME}"
    sh("pveum", "user", "token", "remove", user, TOKEN_NAME, capture=True)   # recreate if it exists
    out = sh("pveum", "user", "token", "add", user, TOKEN_NAME, "--privsep", "1",
             "--comment", "s1screen read-only", "--output-format", "json", capture=True)
    if out.returncode:
        sys.exit(out.stdout)
    secret = json.loads(out.stdout)["value"]
    sh("pveum", "acl", "modify", "/", "--tokens", full, "--roles", "PVEAuditor", check=True)
    config.set_values(path, "pve", {"token_id": full, "token_secret": secret})
    os.chmod(path, 0o600)
    print(f"Created read-only token {full} (role PVEAuditor) and saved it to {path}")
    print(f"已创建只读 Token {full} 并写入 {path}")


def cmd_config(args):
    path = config.ensure(args.config)
    editor = os.environ.get("EDITOR") or next((e for e in ("nano", "vim", "vi", "notepad") if shutil.which(e)), None)
    if not editor:
        sys.exit(f"no editor found, edit {path} manually")
    subprocess.call([editor, str(path)])
    try:
        config.load(path)
        print("config OK / 配置检查通过")
    except Exception as e:  # noqa: BLE001
        print(f"config error / 配置有误: {e}")
        return
    if service_state() == "active" and ask("Restart service now? / 现在重启服务?", True):
        sh("systemctl", "restart", SERVICE)


def cmd_install(args):
    need_root()
    deps = missing_deps()
    if deps:
        print(f"Missing packages: {' '.join(deps)}")
        if not (args.yes or ask("Install them with apt now? / 现在用 apt 安装?", True)):
            sys.exit(1)
        sh("apt-get", "install", "-y", *deps, check=True)
    for unit in legacy_units():
        print(f"Disabling old release service {unit} / 停用旧版服务 {unit}")
        sh("systemctl", "disable", "--now", unit)
    path = config.ensure(args.config)
    cfg = config.load(path)
    if not (cfg["pve"]["token_id"] or cfg["pve"]["password"]) and shutil.which("pveum"):
        if args.yes or ask("No PVE credentials yet. Create a read-only API token? / 创建只读 API Token?", True):
            cmd_token(argparse.Namespace(config=path, user="root@pam"))
    script = (ROOT / "s1screen.py").resolve()
    UNIT_PATH.write_text(UNIT.format(python=sys.executable, script=script, config=Path(path).resolve(), root=ROOT))
    sh("systemctl", "daemon-reload", check=True)
    sh("systemctl", "enable", "--now", SERVICE, check=True)
    time.sleep(2)
    print(f"Installed {UNIT_PATH} and started it: {service_state()}")
    print("已安装并设为开机自启。查看日志: journalctl -u s1screen -f")


def cmd_uninstall(args):
    need_root()
    if UNIT_PATH.exists():
        sh("systemctl", "disable", "--now", SERVICE)
        UNIT_PATH.unlink()
        sh("systemctl", "daemon-reload")
        print("Autostart removed / 已取消开机自启并移除服务")
    else:
        print("Service is not installed / 服务未安装")


def cmd_restart(args):
    need_root()
    sh("systemctl", "restart", SERVICE)
    print(service_state())


def cmd_status(args):
    sh("systemctl", "status", SERVICE, "--no-pager", "-n", "20")


def cmd_led(args):
    from . import led
    cfg = config.load(args.config)
    port = led.resolve_port(args.port or cfg["led"]["port"])
    if not port:
        sys.exit("LED port not found (set [led].port or pass --port)")
    preset = cfg["led"].get(args.mode)
    if preset:
        mode, b, s = preset.get("mode", "off"), preset.get("brightness", 3), preset.get("speed", 3)
    else:
        mode, b, s = args.mode, args.brightness, args.speed
    led.send(port, mode, b, s)
    print(f"{port}: {mode} brightness={b} speed={s}")


# ---- menu ------------------------------------------------------------------
MENU = [
    ("Preview a frame to preview.png", "预览一帧到 preview.png", "preview"),
    ("Edit config", "编辑配置", "config"),
    ("Check devices / PVE / network", "检查设备、PVE 和网络", "check"),
    ("Create read-only PVE API token", "创建只读 PVE API Token", "token"),
    ("Install & enable autostart", "安装并开机自启", "install"),
    ("Disable autostart & remove service", "取消开机自启并移除服务", "uninstall"),
    ("Restart service", "重启服务", "restart"),
    ("Status & recent logs", "状态和最近日志", "status"),
    ("Run in foreground (Ctrl+C to stop)", "前台运行（Ctrl+C 退出）", "run"),
]


def menu(parser, base_args):
    while True:
        print(f"\n== s1screen {__version__} ==  service: {service_state()}  "
              f"config: {'ok' if Path(base_args.config).exists() else 'not created yet'}")
        for i, (en, zh, _) in enumerate(MENU, 1):
            print(f" {i}) {en:38} {zh}")
        print(" 0) Exit                                   退出")
        choice = input("> ").strip()
        if choice in ("0", "q", ""):
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            continue
        name = MENU[int(choice) - 1][2]
        args = parser.parse_args(["--config", str(base_args.config), name])
        try:
            args.func(args)
        except SystemExit as e:
            if e.code not in (None, 0):
                print(e.code)
        except KeyboardInterrupt:
            print()


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="s1screen.py", description="AceMagic S1 front screen for Proxmox VE")
    p.add_argument("-c", "--config", default=str(config.DEFAULT), help="config file (default: config.toml)")
    p.add_argument("-V", "--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run", help="run the screen loop (used by the service)").set_defaults(func=cmd_run)
    sp = sub.add_parser("preview", help="render one frame to a PNG")
    sp.add_argument("-o", "--output", default="preview.png")
    sp.add_argument("--demo", action="store_true", help="use built-in sample data")
    sp.add_argument("--orientation", choices=("portrait", "landscape"))
    sp.add_argument("--scale", type=int, default=2, help="render resolution multiplier")
    sp.set_defaults(func=cmd_preview)
    sub.add_parser("check", help="check config, devices, PVE API and probes").set_defaults(func=cmd_check)
    sp = sub.add_parser("token", help="create a read-only PVE API token and save it to the config")
    sp.add_argument("--user", default="root@pam")
    sp.set_defaults(func=cmd_token)
    sub.add_parser("config", help="edit the config file").set_defaults(func=cmd_config)
    sp = sub.add_parser("install", help="install deps, systemd service and enable autostart")
    sp.add_argument("-y", "--yes", action="store_true")
    sp.set_defaults(func=cmd_install)
    sub.add_parser("uninstall", help="disable autostart and remove the service").set_defaults(func=cmd_uninstall)
    sub.add_parser("restart", help="restart the service").set_defaults(func=cmd_restart)
    sub.add_parser("status", help="service status and recent logs").set_defaults(func=cmd_status)
    sp = sub.add_parser("led", help="set the LED strip: a preset name or a mode")
    sp.add_argument("mode", help="normal|warn|error|night or rainbow|breathing|cycle|auto|off")
    sp.add_argument("brightness", nargs="?", type=int, default=3)
    sp.add_argument("speed", nargs="?", type=int, default=3)
    sp.add_argument("--port")
    sp.set_defaults(func=cmd_led)

    args = p.parse_args(argv)
    if args.cmd:
        return args.func(args)
    if sys.stdin.isatty():
        return menu(p, args)
    return cmd_run(args)
