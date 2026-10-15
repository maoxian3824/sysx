#!/usr/bin/env python3
"""
sysx - 轻量级系统信息与开发辅助 CLI 工具

纯 Python 标准库实现，零第三方依赖。
"""

import argparse
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

__version__ = "1.2.0"

# 系统级常量，用于 /proc 解析
try:
    CLK_TCK = os.sysconf("SC_CLK_TCK")
except (ValueError, OSError, AttributeError):
    CLK_TCK = 100

try:
    PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
except (ValueError, OSError, AttributeError):
    PAGE_SIZE = 4096

# 是否存在 /proc 文件系统（用于跨平台降级提示）
HAS_PROC = os.path.isdir("/proc")

# ---------------------------------------------------------------- ANSI 颜色

class C:
    """ANSI 颜色。是否启用在运行时由 main() 按当前 stdout 判定，
    而非导入时求值，以兼容 stdout 被重定向/替换的场景。"""
    _enabled = True  # 默认启用；main() 启动时会按实际 stdout 重新判定

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    @classmethod
    def disable(cls):
        cls._enabled = False
        for name in ("RESET", "BOLD", "DIM", "RED", "GREEN",
                     "YELLOW", "BLUE", "MAGENTA", "CYAN"):
            setattr(cls, name, "")


def _paint(text, color):
    if not C._enabled:
        return text
    return f"{color}{text}{C.RESET}"


# ---------------------------------------------------------------- 工具函数

def human_bytes(n):
    """把字节数格式化为人类可读形式。负数按 0 处理。"""
    size = float(n)
    if size < 0:
        size = 0.0
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def human_duration(seconds):
    """把秒数格式化为人类可读形式。负值（如时钟回拨）按 0 处理。"""
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def read_text(path):
    """安全读取文本文件，失败返回 None。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _disp_width(text):
    """按显示宽度统计：CJK 等宽字符按 2 计，其余按 1。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(text))


def render_table(headers, rows):
    """渲染对齐的文本表格（表头与数据行使用同一套宽度统计）。"""
    if not rows:
        return ""
    cols = len(headers)
    widths = [_disp_width(h) for h in headers]
    for row in rows:
        for i in range(cols):
            cell = str(row[i]) if i < len(row) else ""
            widths[i] = max(widths[i], _disp_width(cell))

    def pad(text, width):
        text = str(text)
        return text + " " * max(0, width - _disp_width(text))

    out = []
    out.append(_paint("  ".join(pad(h, widths[i]) for i, h in enumerate(headers)),
                      C.BOLD))
    out.append("  ".join("-" * widths[i] for i in range(cols)))
    for row in rows:
        out.append("  ".join(pad(row[i] if i < len(row) else "", widths[i])
                             for i in range(cols)))
    return "\n".join(out)


def emit(data, as_json, renderer):
    """统一输出分发：JSON 模式打印 JSON，否则调用渲染函数并补一个空行。"""
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        renderer(data)
        print()


def section(title):
    """打印小节标题。"""
    print()
    print(_paint(f"▸ {title}", C.BOLD + C.CYAN))


# ---------------------------------------------------------------- info 子命令

def _read_boot_time():
    """从 /proc/stat 的 btime 字段读取真实启动时间（epoch 转 datetime）。"""
    content = read_text("/proc/stat")
    if content:
        for line in content.splitlines():
            if line.startswith("btime "):
                try:
                    return datetime.fromtimestamp(int(line.split()[1]))
                except (ValueError, OSError, OverflowError):
                    return None
    return None


def collect_info(args=None):
    uname = platform.uname()
    boot_time = _read_boot_time()
    uptime_seconds = None

    # Linux: 从 /proc/uptime 取更精确的运行时长；启动时间优先用 btime，
    # 取不到时才用 now - uptime 兜底（后者会受系统时间被修改影响）。
    uptime_raw = read_text("/proc/uptime")
    if uptime_raw:
        try:
            uptime_seconds = float(uptime_raw.split()[0])
            if boot_time is None:
                boot_time = datetime.now() - timedelta(seconds=uptime_seconds)
        except (ValueError, IndexError):
            pass

    load = None
    loadavg = read_text("/proc/loadavg")
    if loadavg:
        parts = loadavg.split()
        if len(parts) >= 3:
            load = [float(parts[0]), float(parts[1]), float(parts[2])]

    cpu_count = os.cpu_count()

    return {
        "hostname": socket.gethostname(),
        "os": {
            "system": uname.system,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "distro": _read_distro(),
        },
        "kernel": uname.release,
        "arch": uname.machine,
        "cpu": {
            "model": _read_cpu_model(),
            "cores": cpu_count,
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "uptime": {
            "seconds": uptime_seconds,
            "human": human_duration(uptime_seconds) if uptime_seconds else None,
            "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S") if boot_time else None,
        },
        "load_average": load,
    }


def _read_distro():
    content = read_text("/etc/os-release")
    if not content:
        return None
    # 合并以反斜杠续行的行（os-release 规范允许）
    merged = []
    pending = ""
    for raw in content.splitlines():
        if raw.endswith("\\"):
            pending += raw[:-1]
        else:
            merged.append(pending + raw)
            pending = ""
    if pending:
        merged.append(pending)

    info = {}
    for line in merged:
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # 仅在首尾成对出现时剥离一层引号，避免误伤值内嵌的引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        # 还原值内的换义符（\n / \t）
        value = value.replace("\\n", "\n").replace("\\t", "\t")
        info[key] = value
    return info.get("PRETTY_NAME") or info.get("NAME")


def _read_cpu_model():
    content = read_text("/proc/cpuinfo")
    if not content:
        return platform.processor() or None
    for line in content.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
        if line.lower().startswith("hardware"):  # ARM 平台
            return line.split(":", 1)[1].strip()
    return platform.processor() or None


def render_info(data):
    print(_paint(f"  {data['hostname']}", C.BOLD + C.MAGENTA))
    print()

    rows = [
        ("操作系统", data["os"]["distro"] or data["os"]["system"]),
        ("内核版本", data["os"]["release"]),
        ("架构", data["os"]["machine"]),
        ("CPU", data["cpu"]["model"] or "未知"),
        ("CPU 核心", data["cpu"]["cores"]),
        ("Python", f"{data['python']['version']} ({data['python']['implementation']})"),
    ]
    if data["uptime"]["human"]:
        rows.append(("运行时长", data["uptime"]["human"]))
    if data["uptime"]["boot_time"]:
        rows.append(("启动时间", data["uptime"]["boot_time"]))
    if data["load_average"]:
        rows.append(("负载 (1/5/15m)", " / ".join(f"{v:.2f}" for v in data["load_average"])))

    print(render_table(["项目", "值"], rows))


# ---------------------------------------------------------------- mem 子命令

def collect_mem(args=None):
    content = read_text("/proc/meminfo")
    if not content:
        # 非 Linux 平台无 /proc，返回结构化结果而非 None，
        # 保证 JSON 消费方拿到的始终是对象
        return {"supported": False, "reason": "当前平台无 /proc/meminfo"}

    raw = {}
    for line in content.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.strip().split()[0]
            try:
                raw[key.strip()] = int(value) * 1024  # kB -> bytes
            except ValueError:
                pass

    total = raw.get("MemTotal", 0)
    free = raw.get("MemFree", 0)
    available = raw.get("MemAvailable", free)
    buffers = raw.get("Buffers", 0)
    cached = raw.get("Cached", 0) + raw.get("SReclaimable", 0)
    used = total - available if total else 0
    percent = (used / total * 100) if total else 0

    swap_total = raw.get("SwapTotal", 0)
    swap_free = raw.get("SwapFree", 0)
    swap_used = swap_total - swap_free

    return {
        "supported": True,
        "total": total,
        "used": used,
        "free": free,
        "available": available,
        "buffers": buffers,
        "cached": cached,
        "percent": round(percent, 1),
        "swap": {
            "total": swap_total,
            "used": swap_used,
            "free": swap_free,
            "percent": round((swap_used / swap_total * 100) if swap_total else 0, 1),
        },
    }


def render_bar(percent, width=30):
    """渲染进度条，按用量着色。percent 会被 clamp 到 [0, 100]，None 视为 0。"""
    if percent is None:
        percent = 0.0
    percent = min(max(float(percent), 0.0), 100.0)
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    if percent >= 90:
        color = C.RED
    elif percent >= 70:
        color = C.YELLOW
    else:
        color = C.GREEN
    return _paint(bar, color)


def render_mem(data):
    if not data or not data.get("supported", True):
        print(_paint("  当前平台不支持内存信息读取（需要 Linux /proc）", C.YELLOW))
        return
    section("内存")
    print(f"  总量  {human_bytes(data['total'])}")
    print(f"  已用  {human_bytes(data['used'])}  {render_bar(data['percent'])}  "
          f"{data['percent']}%")
    print(f"  可用  {human_bytes(data['available'])}")
    print(f"  缓存  {human_bytes(data['cached'])}")
    print(f"  缓冲  {human_bytes(data['buffers'])}")

    section("交换分区")
    if data["swap"]["total"] == 0:
        print("  未启用交换分区")
    else:
        print(f"  总量  {human_bytes(data['swap']['total'])}")
        print(f"  已用  {human_bytes(data['swap']['used'])}  "
              f"{render_bar(data['swap']['percent'])}  {data['swap']['percent']}%")


# ---------------------------------------------------------------- disk 子命令

def _mount_rank(mountpoint):
    """挂载点优先级，用于同一设备多个 bind mount 时择优：
    / 最优先，其次路径越浅越优先，最后按字典序保证稳定。"""
    if mountpoint == "/":
        return (0, 0, "")
    return (1, mountpoint.count("/"), mountpoint)


def collect_disk(args=None):
    # 容器环境中同一设备常被 bind mount 到多个路径。为每个设备挑选
    # 最"根级"的挂载点（优先 /，其次最浅路径），避免保留 /etc/hosts
    # 这类噪音路径而漏掉真正的根分区。
    best = {}
    for part in parse_proc_mounts():
        dev = part["device"]
        if dev not in best or _mount_rank(part["mountpoint"]) < _mount_rank(best[dev]["mountpoint"]):
            best[dev] = part

    mounts = []
    for part in best.values():
        try:
            usage = shutil.disk_usage(part["mountpoint"])
        except OSError:
            continue
        percent = (usage.used / usage.total * 100) if usage.total else 0
        mounts.append({
            "device": part["device"],
            "mountpoint": part["mountpoint"],
            "fstype": part["fstype"],
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(percent, 1),
        })
    mounts.sort(key=lambda m: m["percent"], reverse=True)
    return mounts


def parse_proc_mounts():
    """从 /proc/mounts 解析挂载点，只保留真实块设备。"""
    content = read_text("/proc/mounts")
    if not content:
        return []

    skip_fs = {
        "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2",
        "overlay", "squashfs", "autofs", "mqueue", "hugetlbfs", "debugfs",
        "tracefs", "securityfs", "pstore", "bpf", "configfs", "fusectl",
        "binfmt_misc", "rpc_pipefs", "nsfs", "ramfs", "efivarfs",
    }
    seen = set()
    result = []
    for line in content.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        device, mountpoint, fstype = fields[0], fields[1], fields[2]
        if fstype in skip_fs:
            continue
        if not device.startswith("/dev/"):
            continue
        # 跳过容器/快照层的噪音挂载点
        if mountpoint.startswith(("/.oldroot", "/.PlnPyKFp4CRfFtgC1",
                                  "/snap/", "/var/lib/docker/")):
            continue
        if mountpoint in seen:
            continue
        seen.add(mountpoint)
        mountpoint = _unescape_mount(mountpoint)
        result.append({"device": device, "mountpoint": mountpoint, "fstype": fstype})
    return result


def _unescape_mount(s):
    """解码 /proc/mounts 中的八进制转义（\\040=空格, \\011=Tab, \\134=反斜杠）。"""
    return re.sub(r"\\(\d{3})", lambda m: chr(int(m.group(1), 8)), s)


def render_disk(data):
    if not data:
        if HAS_PROC:
            print("未找到可用的块设备挂载点")
        else:
            print("当前平台不支持磁盘信息（需要 Linux /proc/mounts）")
        return
    rows = []
    for m in data:
        rows.append([
            m["mountpoint"],
            m["device"],
            m["fstype"],
            human_bytes(m["total"]),
            human_bytes(m["used"]),
            human_bytes(m["free"]),
            f"{m['percent']}%",
        ])
    print(render_table(
        ["挂载点", "设备", "类型", "总量", "已用", "可用", "使用率"], rows))


# ---------------------------------------------------------------- proc 子命令

def _read_proc_stat(pid_str):
    """读取单个进程的 stat，返回 (comm, state, cpu_ticks, rss_bytes)。"""
    stat = read_text(f"/proc/{pid_str}/stat")
    if not stat:
        return None
    rparen = stat.rfind(")")
    if rparen < 0:
        return None
    open_paren = stat.find("(")
    if open_paren < 0 or open_paren > rparen:
        return None
    comm = stat[open_paren + 1:rparen]
    rest = stat[rparen + 2:].split()
    if len(rest) < 22:
        return None
    try:
        state = rest[0]
        utime = int(rest[11])
        stime = int(rest[12])
        rss_pages = int(rest[21])
    except (ValueError, IndexError):
        return None
    return {
        "name": comm,
        "state": state,
        "cpu_ticks": utime + stime,
        "rss": rss_pages * PAGE_SIZE,
    }


def _read_total_cpu_ticks():
    """读取系统整体累计 CPU tick 数。"""
    content = read_text("/proc/stat")
    if not content:
        return None
    first = content.splitlines()[0]
    if not first.startswith("cpu "):
        return None
    try:
        return sum(int(x) for x in first.split()[1:])
    except ValueError:
        return None


def collect_proc(limit=10, sort_by="cpu", interval=0.25):
    """采样两次 /proc/stat，计算进程在采样窗口内的真实 CPU 占用率。"""
    num_cpus = os.cpu_count() or 1

    total_mem = 0
    meminfo = read_text("/proc/meminfo")
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                try:
                    total_mem = int(line.split()[1]) * 1024
                except (ValueError, IndexError):
                    pass

    def snapshot():
        try:
            pids = [e for e in os.listdir("/proc") if e.isdigit()]
        except OSError:
            return {}
        data = {}
        for pid_str in pids:
            info = _read_proc_stat(pid_str)
            if info is not None:
                data[pid_str] = info
        return data

    first = snapshot()
    first_total = _read_total_cpu_ticks()
    time.sleep(interval)
    second = snapshot()
    second_total = _read_total_cpu_ticks()

    if not second:
        return []

    # 窗口内系统总 tick 增量
    delta_total = 0
    if first_total is not None and second_total is not None:
        delta_total = second_total - first_total
    window_ticks = delta_total if delta_total > 0 else num_cpus * CLK_TCK * interval

    procs = []
    for pid_str, cur in second.items():
        prev = first.get(pid_str)
        delta = cur["cpu_ticks"] - prev["cpu_ticks"] if prev else cur["cpu_ticks"]
        if delta < 0:
            delta = 0
        # 单核 100% 为满，允许超过 100%（多线程进程）
        cpu_percent = delta / window_ticks * num_cpus * 100 if window_ticks else 0.0
        cpu_percent = min(cpu_percent, num_cpus * 100)
        procs.append({
            "pid": int(pid_str),
            "name": cur["name"],
            "state": cur["state"],
            "cpu_percent": round(cpu_percent, 1),
            "rss": cur["rss"],
            # 读不到 MemTotal 时标记为 None，避免把"无数据"误显示成 0%
            "mem_percent": round(cur["rss"] / total_mem * 100, 2) if total_mem else None,
        })

    key = "rss" if sort_by == "mem" else "cpu_percent"
    procs.sort(key=lambda p: p[key], reverse=True)
    return procs[:limit]


def render_proc(data):
    if not data:
        if HAS_PROC:
            print("未读到进程信息")
        else:
            print("当前平台不支持进程信息（需要 Linux /proc 文件系统）")
        return
    rows = []
    for p in data:
        rows.append([
            p["pid"],
            p["name"][:28],
            p["state"],
            f"{p['cpu_percent']}%",
            human_bytes(p["rss"]),
            f"{p['mem_percent']}%" if p["mem_percent"] is not None else "-",
        ])
    print(render_table(["PID", "名称", "状态", "CPU", "内存", "内存占比"], rows))


# ---------------------------------------------------------------- net 子命令

def collect_net(args=None):
    info = {
        "hostname": socket.gethostname(),
        "interfaces": [],
        "dns": [],
    }

    # 从 /sys/class/net 读取网卡
    try:
        for name in sorted(os.listdir("/sys/class/net")):
            iface = {"name": name, "address": None, "state": None, "speed": None}
            addr = read_text(f"/sys/class/net/{name}/address")
            if addr:
                iface["address"] = addr.strip()
            state = read_text(f"/sys/class/net/{name}/operstate")
            if state:
                iface["state"] = state.strip()
            try:
                with open(f"/sys/class/net/{name}/speed", encoding="utf-8") as fh:
                    speed = int(fh.read().strip())
                    # 未连接/虚拟网卡返回负数；内核用 0xFFFFFFFF 表示速率未知
                    iface["speed"] = speed if 0 < speed < 0xFFFFFFFF else None
            except (OSError, ValueError):
                pass
            info["interfaces"].append(iface)
    except OSError:
        pass

    # 主机 IP（通过 UDP 连接探测，不会真的发包）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))
            info["local_ip"] = sock.getsockname()[0]
    except (OSError, socket.error):
        info["local_ip"] = None

    # DNS 服务器
    resolv = read_text("/etc/resolv.conf")
    if resolv:
        for line in resolv.splitlines():
            line = line.strip()
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    info["dns"].append(parts[1])

    return info


def render_net(data):
    print(_paint(f"  主机名  {data['hostname']}", C.BOLD))
    if data.get("local_ip"):
        print(f"  默认出口 IP  {_paint(data['local_ip'], C.GREEN)}")
    if data.get("dns"):
        print(f"  DNS     {', '.join(data['dns'])}")

    section("网络接口")
    if not data["interfaces"]:
        print("  未找到网络接口")
        return
    rows = []
    for i in data["interfaces"]:
        speed = f"{i['speed']} Mb/s" if i.get("speed") else "-"
        state = i.get("state") or "-"
        if state == "up":
            state = _paint(state, C.GREEN)
        elif state == "down":
            state = _paint(state, C.DIM)
        rows.append([i["name"], i.get("address") or "-", state, speed])
    print(render_table(["接口", "MAC 地址", "状态", "速率"], rows))


# ---------------------------------------------------------------- env 子命令

def collect_env(args=None):
    interesting = [
        "SHELL", "TERM", "LANG", "LC_ALL", "USER", "HOME", "PATH",
        "EDITOR", "VISUAL", "PAGER", "TZ", "PWD", "SSH_CONNECTION",
        "VIRTUAL_ENV", "PYTHONPATH", "NODE_ENV", "GOPATH", "VIRTUAL_ENV_PROMPT",
    ]
    found = {}
    for key in interesting:
        value = os.environ.get(key)
        if value:
            found[key] = value
    # 额外收录所有以常见前缀开头的变量
    for key, value in sorted(os.environ.items()):
        if key in found:
            continue
        if key.startswith(("PYTHON", "PIP", "NPM", "CARGO", "GO", "RUST", "JAVA", "DOCKER")):
            found[key] = value
    return found


def render_env(data):
    if not data:
        print("未找到相关环境变量")
        return
    rows = [[k, v if len(v) < 70 else v[:67] + "..."] for k, v in sorted(data.items())]
    print(render_table(["变量", "值"], rows))


# ---------------------------------------------------------------- ports 子命令

def _decode_ipv6(addr_hex):
    """把 /proc/net/*6 的 32 位十六进制 IPv6 地址解码为标准字符串。
    内核按 4 个 u32 存储、每个 u32 内小端，故每组 4 字节需反转。"""
    try:
        raw = bytes.fromhex(addr_hex)
    except ValueError:
        return "?"
    if len(raw) != 16:
        return "?"
    ordered = bytes(b for i in range(0, 16, 4) for b in raw[i:i + 4][::-1])
    return ipaddress.IPv6Address(ordered).compressed


def collect_ports(args=None):
    """解析监听/绑定的端口：
    TCP / TCP6 取 LISTEN（状态 0A）；UDP / UDP6 取已绑定的未连接
    socket（状态 07，即 UDP 的"监听"）。"""
    ports = []
    specs = (
        ("tcp", "/proc/net/tcp", "0A"),
        ("tcp6", "/proc/net/tcp6", "0A"),
        ("udp", "/proc/net/udp", "07"),
        ("udp6", "/proc/net/udp6", "07"),
    )
    for proto, path, listen_state in specs:
        content = read_text(path)
        if not content:
            continue
        lines = content.splitlines()[1:]  # 跳过表头
        for line in lines:
            fields = line.split()
            if len(fields) < 4:
                continue
            local = fields[1]
            state = fields[3]
            if state != listen_state:
                continue
            try:
                addr_hex, port_hex = local.rsplit(":", 1)
                port = int(port_hex, 16)
            except ValueError:
                continue
            try:
                if proto.endswith("6"):
                    ip = _decode_ipv6(addr_hex)
                else:
                    ip = ".".join(str(int(addr_hex[i:i + 2], 16))
                                  for i in (6, 4, 2, 0))
            except ValueError:
                ip = "?"

            ports.append({
                "proto": proto,
                "address": ip,
                "port": port,
                "inode": fields[9] if len(fields) > 9 else None,
            })

    # 去重并按协议+端口排序
    uniq = {}
    for p in ports:
        uniq[(p["proto"], p["port"])] = p
    return sorted(uniq.values(), key=lambda p: (p["proto"], p["port"]))


def render_ports(data):
    if not data:
        if HAS_PROC:
            print("未发现监听/绑定的端口")
        else:
            print("当前平台不支持端口信息（需要 Linux /proc/net）")
        return
    rows = [[p["proto"], p["address"], p["port"]] for p in data]
    print(render_table(["协议", "监听地址", "端口"], rows))


# ---------------------------------------------------------------- uptime 子命令

def collect_uptime(args=None):
    raw = read_text("/proc/uptime")
    load = read_text("/proc/loadavg")
    result = {"seconds": None, "human": None, "load": None}
    if raw:
        try:
            result["seconds"] = float(raw.split()[0])
            result["human"] = human_duration(result["seconds"])
        except (ValueError, IndexError):
            pass
    if load:
        parts = load.split()
        if len(parts) >= 3:
            result["load"] = [float(parts[0]), float(parts[1]), float(parts[2])]
    return result


def render_uptime(data):
    if not data["human"]:
        print("无法读取运行时间")
        return
    print(f"  运行时长  {_paint(data['human'], C.BOLD + C.GREEN)}")
    if data["load"]:
        print(f"  负载    {_paint(' / '.join(f'{v:.2f}' for v in data['load']), C.CYAN)}"
              f"   {_paint('(1 / 5 / 15 分钟)', C.DIM)}")


# ---------------------------------------------------------------- doctor 子命令

def _check_dns():
    """尝试解析几个常见域名，任一成功即认为 DNS 可用。"""
    for host in ("example.com", "github.com", "cloudflare.com"):
        try:
            ip = socket.gethostbyname(host)
            return True, f"{host} → {ip}"
        except (OSError, socket.error):
            continue
    return False, "所有域名解析均失败"


def _probe_tcp(target, timeout=3):
    """探测单个 TCP 目标，返回 (ok, detail)。"""
    host, port = target
    try:
        # 用 with 确保异常路径下 socket 也会被关闭
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
        return True, f"可访问 {host}:{port}"
    except (OSError, socket.error) as exc:
        return False, str(exc)


def _check_network(timeout=3):
    """多目标 TCP 并发探测，任一可达即认为外网连通。
    并发后断网最坏耗时约 timeout，而非 timeout × 目标数。"""
    targets = [("1.1.1.1", 443), ("8.8.8.8", 53), ("223.5.5.5", 443)]
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        results = [f.result() for f in (pool.submit(_probe_tcp, t, timeout)
                                        for t in targets)]
    for ok, detail in results:
        if ok:
            return True, detail
    detail = next((d for ok, d in results if d), "连接失败")
    return False, detail[:60]


def _is_root():
    """是否 root；平台不支持（如 Windows 无 geteuid）时返回 None。"""
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return None
    try:
        return geteuid() == 0
    except OSError:
        return None


def collect_doctor(args=None):
    """开发环境体检。"""
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": ok, "detail": detail})

    # Python
    check("Python", True, f"{platform.python_version()} ({sys.executable})")

    # 常用开发工具
    tools = ["git", "curl", "wget", "gcc", "make", "docker", "node", "npm",
             "go", "rustc", "java", "vim", "tmux"]
    for tool in tools:
        path = shutil.which(tool)
        check(tool, path is not None, path or "未安装")

    # 权限（Windows 无 geteuid，跳过而非误报失败）
    root = _is_root()
    if root is None:
        check("root 权限", True, "当前平台不支持该检查")
    else:
        check("root 权限", root, "当前是 root" if root else "普通用户")

    # 网络探测：DNS 与外网连通并发执行，缩短断网环境下的等待
    with ThreadPoolExecutor(max_workers=2) as pool:
        dns_future = pool.submit(_check_dns)
        net_future = pool.submit(_check_network)
        dns_ok, dns_detail = dns_future.result()
        net_ok, net_detail = net_future.result()
    check("DNS 解析", dns_ok, dns_detail)
    check("外网连通", net_ok, net_detail)

    # 磁盘余量
    try:
        usage = shutil.disk_usage("/")
        free_percent = usage.free / usage.total * 100
        check("根分区余量", free_percent > 10,
              f"{human_bytes(usage.free)} 可用 ({free_percent:.1f}%)")
    except OSError:
        pass

    # 内存余量
    mem = collect_mem()
    if mem and mem.get("supported", True):
        check("内存余量", mem["percent"] < 90,
              f"{human_bytes(mem['available'])} 可用")

    return checks


def render_doctor(data):
    if not data:
        print("无检查项")
        return
    passed = sum(1 for c in data if c["ok"])
    for c in data:
        mark = _paint("✓", C.GREEN) if c["ok"] else _paint("✗", C.RED)
        name = c["name"].ljust(14)
        detail = c["detail"]
        if not c["ok"]:
            detail = _paint(detail, C.DIM)
        print(f"  {mark} {name} {detail}")

    print()
    total = len(data)
    color = C.GREEN if passed == total else C.YELLOW
    print(_paint(f"  {passed}/{total} 项通过", color + C.BOLD))


# ---------------------------------------------------------------- CLI 定义

def build_parser():
    parser = argparse.ArgumentParser(
        prog="sysx",
        description="轻量级系统信息与开发辅助 CLI 工具",
        epilog="示例:  sysx info       显示系统概览\n"
               "       sysx mem -j    以 JSON 输出内存信息\n"
               "       sysx doctor    检查开发环境",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version",
                        version=f"sysx {__version__}")
    parser.add_argument("--debug", action="store_true",
                        help="发生错误时打印完整堆栈信息")

    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    def add(name, help_text, collector, renderer, extra=None):
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("-j", "--json", action="store_true",
                       help="以 JSON 格式输出")
        if extra:
            extra(p)
        p.set_defaults(collector=collector, renderer=renderer)

    add("info", "显示系统概览信息", collect_info, render_info)
    add("mem", "显示内存与交换分区使用情况", collect_mem, render_mem)
    add("disk", "显示磁盘挂载点与使用率", collect_disk, render_disk)

    def proc_extra(p):
        p.add_argument("-n", "--limit", type=int, default=10,
                       help="显示条数 (默认 10)")
        p.add_argument("-s", "--sort", choices=["cpu", "mem"], default="cpu",
                       help="排序依据 (默认 cpu)")

    def proc_collect(args):
        return collect_proc(limit=args.limit, sort_by=args.sort)

    add("proc", "显示占用最高的进程", proc_collect, render_proc,
        extra=proc_extra)

    add("net", "显示网络接口与 DNS 信息", collect_net, render_net)
    add("env", "显示相关环境变量", collect_env, render_env)
    add("ports", "显示监听/绑定的 TCP 与 UDP 端口", collect_ports, render_ports)
    add("uptime", "显示系统运行时长与负载", collect_uptime, render_uptime)
    add("doctor", "检查开发环境完整性", collect_doctor, render_doctor)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    # 颜色状态在运行时按当前 stdout 判定（而非导入时），兼容 stdout
    # 被重定向/替换的场景；NO_COLOR 约定依旧生效。
    C._enabled = bool(sys.stdout.isatty()) and not os.environ.get("NO_COLOR")

    try:
        data = args.collector(args)
        emit(data, args.json, args.renderer)
    except BrokenPipeError:
        # 下游管道提前关闭（如 `sysx info | head`）：静默优雅退出，
        # 并把 stdout 重定向到 devnull，避免解释器退出时再次 flush 报错。
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except Exception as exc:  # 单项失败给友好提示，不暴露 traceback
        if getattr(args, "debug", False):
            raise
        print(f"sysx: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("（加 --debug 可查看完整堆栈）", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        os._exit(0)
