#!/usr/bin/env python3
"""
sysx - 轻量级系统信息与开发辅助 CLI 工具

纯 Python 标准库实现，零第三方依赖。
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta

__version__ = "1.0.0"

# 系统级常量，用于 /proc 解析
try:
    CLK_TCK = os.sysconf("SC_CLK_TCK")
except (ValueError, OSError, AttributeError):
    CLK_TCK = 100

try:
    PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
except (ValueError, OSError, AttributeError):
    PAGE_SIZE = 4096

# ---------------------------------------------------------------- ANSI 颜色

class C:
    """ANSI 颜色。当输出不是 TTY 或设置了 NO_COLOR 时自动禁用。"""
    _enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

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
    """把字节数格式化为人类可读形式。"""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def human_duration(seconds):
    """把秒数格式化为人类可读形式。"""
    seconds = int(seconds)
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
    except (OSError, IOError):
        return None


def render_table(headers, rows):
    """渲染对齐的文本表格。"""
    if not rows:
        return ""
    cols = len(headers)
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i in range(cols):
            cell = str(row[i]) if i < len(row) else ""
            # 中文等宽字符粗略按 2 个宽度计算
            width = sum(2 if ord(ch) > 0x2E80 else 1 for ch in cell)
            widths[i] = max(widths[i], width)

    def pad(text, width):
        text = str(text)
        cur = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)
        return text + " " * max(0, width - cur)

    out = []
    out.append(_paint("  ".join(pad(h, widths[i]) for i, h in enumerate(headers)),
                      C.BOLD))
    out.append("  ".join("-" * widths[i] for i in range(cols)))
    for row in rows:
        out.append("  ".join(pad(row[i] if i < len(row) else "", widths[i])
                             for i in range(cols)))
    return "\n".join(out)


def emit(data, as_json, renderer):
    """统一输出分发：JSON 模式下打印 JSON，否则调用渲染函数。"""
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        renderer(data)


def section(title):
    """打印小节标题。"""
    print()
    print(_paint(f"▸ {title}", C.BOLD + C.CYAN))


# ---------------------------------------------------------------- info 子命令

def collect_info(args=None):
    uname = platform.uname()
    boot_time = None
    uptime_seconds = None

    # Linux: 从 /proc/uptime 取更精确的运行时长
    uptime_raw = read_text("/proc/uptime")
    if uptime_raw:
        try:
            uptime_seconds = float(uptime_raw.split()[0])
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
    info = {}
    for line in content.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip().strip('"')
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
        return None

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
    """渲染进度条，按用量着色。"""
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
    if not data:
        print("无法读取内存信息（需要 Linux /proc 文件系统）")
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

def collect_disk(args=None):
    mounts = []
    seen_devices = set()
    for part in psutil_like_partitions():
        # 容器环境中同一块设备常被 bind mount 到多个路径，按设备去重
        if part["device"] in seen_devices:
            continue
        seen_devices.add(part["device"])
        try:
            usage = shutil.disk_usage(part["mountpoint"])
        except (OSError, IOError):
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


def psutil_like_partitions():
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
        # 反转义 /proc/mounts 中的八进制转义
        mountpoint = (mountpoint.replace("\\040", " ")
                                .replace("\\011", "\t")
                                .replace("\\012", "\n"))
        result.append({"device": device, "mountpoint": mountpoint, "fstype": fstype})
    return result


def render_disk(data):
    if not data:
        print("未找到可用的块设备挂载点")
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
            "mem_percent": round(cur["rss"] / total_mem * 100, 2) if total_mem else 0,
        })

    key = "rss" if sort_by == "mem" else "cpu_percent"
    procs.sort(key=lambda p: p[key], reverse=True)
    return procs[:limit]


def render_proc(data):
    if not data:
        print("未读到进程信息（需要 Linux /proc 文件系统）")
        return
    rows = []
    for p in data:
        rows.append([
            p["pid"],
            p["name"][:28],
            p["state"],
            f"{p['cpu_percent']}%",
            human_bytes(p["rss"]),
            f"{p['mem_percent']}%",
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
                with open(f"/sys/class/net/{name}/speed") as fh:
                    speed = int(fh.read().strip())
                    # 网卡未连接或虚拟网卡时内核返回负数
                    iface["speed"] = speed if speed > 0 else None
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
        print(f"  本机 IP  {_paint(data['local_ip'], C.GREEN)}")
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

def collect_ports(args=None):
    """从 /proc/net/tcp 解析监听端口。"""
    ports = []
    for proto, path in (("tcp", "/proc/net/tcp"), ("tcp6", "/proc/net/tcp6")):
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
            if state != "0A":  # 0A = LISTEN
                continue
            try:
                addr_hex, port_hex = local.rsplit(":", 1)
                port = int(port_hex, 16)
            except ValueError:
                continue
            try:
                if proto == "tcp":
                    ip = ".".join(str(int(addr_hex[i:i + 2], 16))
                                  for i in (6, 4, 2, 0))
                else:
                    ip = "::"
                    if addr_hex == "0" * 32:
                        ip = "[::]"
            except ValueError:
                ip = "?"

            ports.append({
                "proto": proto,
                "address": ip,
                "port": port,
                "inode": fields[9] if len(fields) > 9 else None,
            })

    # 去重并按端口排序
    uniq = {}
    for p in ports:
        uniq[(p["proto"], p["port"])] = p
    return sorted(uniq.values(), key=lambda p: p["port"])


def render_ports(data):
    if not data:
        print("未发现监听中的 TCP 端口")
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


def _check_network():
    """多目标 TCP 探测，任一可达即认为外网连通。"""
    targets = [("1.1.1.1", 443), ("8.8.8.8", 53), ("223.5.5.5", 443)]
    errors = []
    for host, port in targets:
        try:
            # 用 with 确保异常路径下 socket 也会被关闭
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect((host, port))
            return True, f"可访问 {host}:{port}"
        except (OSError, socket.error) as exc:
            errors.append(str(exc))
            continue
    detail = errors[0] if errors else "连接失败"
    return False, detail[:60]


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

    # 权限
    check("root 权限", os.geteuid() == 0,
          "当前是 root" if os.geteuid() == 0 else "普通用户")

    # 网络探测
    dns_ok, dns_detail = _check_dns()
    check("DNS 解析", dns_ok, dns_detail)

    net_ok, net_detail = _check_network()
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
    if mem:
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

    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    def add(name, help_text, func, collector, renderer, extra=None):
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("-j", "--json", action="store_true",
                       help="以 JSON 格式输出")
        if extra:
            extra(p)
        p.set_defaults(func=func, collector=collector, renderer=renderer)

    add("info", "显示系统概览信息", None, collect_info, render_info)
    add("mem", "显示内存与交换分区使用情况", None, collect_mem, render_mem)
    add("disk", "显示磁盘挂载点与使用率", None, collect_disk, render_disk)

    def proc_extra(p):
        p.add_argument("-n", "--limit", type=int, default=10,
                       help="显示条数 (默认 10)")
        p.add_argument("-s", "--sort", choices=["cpu", "mem"], default="cpu",
                       help="排序依据 (默认 cpu)")

    def proc_collect(args):
        return collect_proc(limit=args.limit, sort_by=args.sort)

    add("proc", "显示占用最高的进程", None, proc_collect, render_proc,
        extra=proc_extra)

    add("net", "显示网络接口与 DNS 信息", None, collect_net, render_net)
    add("env", "显示相关环境变量", None, collect_env, render_env)
    add("ports", "显示监听中的 TCP 端口", None, collect_ports, render_ports)
    add("uptime", "显示系统运行时长与负载", None, collect_uptime, render_uptime)
    add("doctor", "检查开发环境完整性", None, collect_doctor, render_doctor)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if getattr(args, "json", False) and not sys.stdout.isatty():
        C.disable()

    data = args.collector(args)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        args.renderer(data)
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
