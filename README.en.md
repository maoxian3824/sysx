# sysx

> 中文版：[README.md](README.md)

> Lightweight system-info & developer-assistant CLI — pure Python standard library, zero third-party dependencies.

[![Tests](https://github.com/maoxian3824/sysx/actions/workflows/test.yml/badge.svg)](https://github.com/maoxian3824/sysx/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/sysx-cli.svg)](https://pypi.org/project/sysx-cli/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#)

`sysx` consolidates the scattered commands you reach for when triaging a system —
`top`, `df`, `free`, `ip`, `ss` — into one unified, readable, JSON-friendly set of
subcommands. Great for CI scripts, container images, or simply remembering fewer flags.

## Features

- **Zero dependencies** — standard library only; `pip install` pulls nothing extra
- **JSON output** — every subcommand supports `-j`, ready for `jq` or scripts
- **Auto color** — colored in a terminal; auto-disabled when redirected to a file or pipe
- **Read-only & safe** — only reads `/proc` and `/sys`; never modifies anything
- **Graceful degradation** — full on Linux; degrades cleanly on macOS / Windows without errors

## Installation

> **Package name vs command name**: the PyPI distribution is `sysx-cli` (the name
> `sysx` is already taken), but the command you run after installing is still `sysx`.

### Method 1: pip (recommended)

```bash
pip install sysx-cli
sysx info
```

> **Note for users behind a PyPI mirror (e.g. in China):** a freshly published
> release can take several minutes to sync to mirrors. If
> `pip install sysx-cli` reports "No matching distribution found", install directly
> from the official index instead:
> `pip install sysx-cli -i https://pypi.org/simple`

### Method 2: Run the single file (no install)

```bash
curl -LO https://raw.githubusercontent.com/maoxian3824/sysx/master/sysx.py
python3 sysx.py info
```

### Method 3: From source

```bash
git clone https://github.com/maoxian3824/sysx.git
cd sysx
python3 sysx.py info
```

### Method 4: From a GitHub Release

```bash
curl -LO https://github.com/maoxian3824/sysx/releases/latest/download/sysx_cli-1.0.0-py3-none-any.whl
pip install sysx_cli-1.0.0-py3-none-any.whl
```

## Usage

```
sysx <command> [options]
```

### Subcommands

| Command | Description |
|---|---|
| `info` | System overview: OS, kernel, CPU, memory, uptime, load |
| `mem` | Memory & swap usage (with a progress bar) |
| `disk` | Disk mounts & usage (sorted by usage) |
| `proc` | Top processes, sortable by CPU / memory |
| `net` | Network interfaces, MAC, link status, local IP, DNS |
| `ports` | Listening TCP ports |
| `env` | Relevant environment variables (shell, toolchains, containers) |
| `uptime` | Uptime and 1/5/15-minute load |
| `doctor` | Dev-environment checkup: toolchains, network, disk headroom |

### Examples

**System overview**

```console
$ sysx info
  16b3429714a6

项目            值
--------------  -------------------------------
操作系统        Ubuntu 24.04.3 LTS
内核版本        6.6.117-45.11.6.tl4.x86_64
架构            x86_64
CPU             AMD EPYC 9K84 96-Core Processor
CPU 核心        32
Python          3.11.1 (CPython)
运行时长        1h 41m 33s
启动时间        2026-10-06 17:45:39
负载 (1/5/15m)  2.78 / 2.16 / 2.24
```

> The human-readable table labels above are printed in **Chinese** in the current
> build. For language-neutral output, use `-j` (JSON) — the keys are always English,
> as shown below.

**JSON output (with jq)**

```bash
# memory usage percentage
sysx mem -j | jq '.percent'

# top 3 processes by memory
sysx proc -j -n 3 -s mem | jq -r '.[].name'

# list all listening port numbers
sysx ports -j | jq -r '.[].port'
```

**Memory**

```console
$ sysx mem

▸ 内存
  总量  123.3 GB
  已用  16.5 GB  ████░░░░░░░░░░░░░░░░░░░░░░░░░░  13.4%
  可用  106.8 GB
  缓存  97.0 GB
  缓冲  1.4 GB

▸ 交换分区
  未启用交换分区
```

**Top processes (by CPU)**

```console
$ sysx proc -n 5
PID   名称             状态  CPU   内存      内存占比
----  ---------------  --  ----  --------  -----
1323  envd             S   8.0%  15.9 MB   0.01%
62    supervisord      S   0.0%  13.8 MB   0.01%
91    node             S   0.0%  55.7 MB   0.04%
```

**Dev-environment checkup**

```console
$ sysx doctor
  ✓ Python         3.11.1 (/usr/bin/python3)
  ✓ git            /usr/bin/git
  ✓ docker         /usr/local/bin/docker
  ✗ tmux           not installed
  ✓ root 权限       当前是 root
  ✓ DNS 解析        example.com → 172.66.147.243
  ✓ 外网连通         可访问 8.8.8.8:53
  ✓ 根分区余量        254.0 GB 可用 (99.2%)

  18/19 passed
```

## Options

| Option | Applies to | Description |
|---|---|---|
| `-j, --json` | all | Output as JSON |
| `-n, --limit N` | `proc` | Number of rows (default 10) |
| `-s, --sort {cpu,mem}` | `proc` | Sort key (default `cpu`) |
| `-V, --version` | global | Show version |
| `-h, --help` | global | Show help |

## Environment variables

| Variable | Effect |
|---|---|
| `NO_COLOR` | When set, disables colored output (per [no-color.org](https://no-color.org/)) |

## Implementation notes

`sysx` avoids libraries like `psutil` and reads the kernel-exposed interfaces directly:

| Data | Source |
|---|---|
| Memory | `/proc/meminfo` |
| Uptime | `/proc/uptime` |
| Load | `/proc/loadavg` |
| Process list | `/proc/<pid>/stat` |
| CPU usage | delta of two `/proc/stat` samples |
| Disk mounts | `/proc/mounts` + `shutil.disk_usage` |
| Network interfaces | `/sys/class/net/*` |
| DNS | `/etc/resolv.conf` |
| Listening ports | `/proc/net/tcp`, `/proc/net/tcp6` |

**On CPU usage:** reading `/proc/<pid>/stat` directly only yields a process's
cumulative CPU time; dividing by the total gives a wrong result (long-running
processes are badly overestimated). `sysx` samples twice (250 ms apart) and
computes the delta ratio, matching `top`.

**Container awareness:** in Docker / Kubernetes, `/proc/mounts` is full of bind
mounts — the same device can appear dozens of times. `sysx` de-duplicates by
device and filters snapshot-layer mounts, yielding a clean disk list.

## Compatibility

| Platform | Status |
|---|---|
| Linux | Full support |
| macOS | Partial (no `/proc`; `info`/`disk`/`doctor` work) |
| Windows | Basic (`info`/`doctor` work) |

## Development

```bash
# Run the test suite (46 cases, pure stdlib unittest)
python3 -m unittest discover -s tests -v

# Strict mode: resource leaks are errors
python3 -W error::ResourceWarning -m unittest discover -s tests

# Build & validate
python3 -m build
python3 -m twine check dist/*      # PyPI metadata check
python3 scripts/check_no_deps.py   # zero-dependency check
```

CI runs the above on Python 3.8–3.12 and macOS automatically; see
[.github/workflows/test.yml](.github/workflows/test.yml).

Full PyPI release instructions: [PUBLISHING.md](PUBLISHING.md).

## License

MIT
