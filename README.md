# sysx

> English version: [README.en.md](README.en.md)

> 轻量级系统信息与开发辅助 CLI 工具 — 纯 Python 标准库实现，零第三方依赖。

[![Tests](https://github.com/maoxian3824/sysx/actions/workflows/test.yml/badge.svg)](https://github.com/maoxian3824/sysx/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/sysx-cli.svg)](https://pypi.org/project/sysx-cli/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#)

`sysx` 把日常排查系统状态时零散用到的 `top`、`df`、`free`、`ip`、`ss` 等命令，
收敛成一套统一、可读、支持 JSON 输出的子命令集。适合放进 CI 脚本、容器镜像，
或者单纯想少记几个命令参数的时候。

## 特性

- **零依赖** — 只用 Python 标准库，`pip install` 不需要拉任何第三方包
- **JSON 输出** — 每个子命令都支持 `-j`，方便喂给 `jq` 或脚本解析
- **自动配色** — 输出到终端时着色；重定向到文件或管道时自动禁用
- **只读安全** — 全部操作仅读取 `/proc`、`/sys`，不做任何修改
- **跨平台降级** — Linux 下功能最全，macOS / Windows 下优雅降级不报错

## 安装

> **包名 vs 命令名**：PyPI 发行名是 `sysx-cli`（`sysx` 已被占用），
> 但安装后的运行命令仍是 `sysx`。

### 方式一：pip 安装（推荐）

```bash
pip install sysx-cli
sysx info
```

### 方式二：直接运行单文件（无需安装）

```bash
curl -LO https://raw.githubusercontent.com/maoxian3824/sysx/master/sysx.py
python3 sysx.py info
```

### 方式三：从源码

```bash
git clone https://github.com/maoxian3824/sysx.git
cd sysx
python3 sysx.py info
```

### 方式四：从 GitHub Release 安装

```bash
curl -LO https://github.com/maoxian3824/sysx/releases/latest/download/sysx_cli-1.0.0-py3-none-any.whl
pip install sysx_cli-1.0.0-py3-none-any.whl
```

## 使用

```
sysx <命令> [选项]
```

### 子命令一览

| 命令 | 说明 |
|---|---|
| `info` | 系统概览：OS、内核、CPU、内存、运行时长、负载 |
| `mem` | 内存与交换分区使用情况（带进度条） |
| `disk` | 磁盘挂载点与使用率（按使用率排序） |
| `proc` | 占用最高的进程，可按 CPU / 内存排序 |
| `net` | 网络接口、MAC、链路状态、本机 IP、DNS |
| `ports` | 监听中的 TCP 端口 |
| `env` | 相关环境变量（Shell、语言工具链、容器等） |
| `uptime` | 运行时长与 1/5/15 分钟负载 |
| `doctor` | 开发环境体检：工具链、网络、磁盘余量 |

### 示例

**系统概览**

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

**内存**

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

**进程（按 CPU 排序）**

```console
$ sysx proc -n 5
PID   名称             状态  CPU   内存      内存占比
----  ---------------  --  ----  --------  -----
1323  envd             S   8.0%  15.9 MB   0.01%
62    supervisord      S   0.0%  13.8 MB   0.01%
91    node             S   0.0%  55.7 MB   0.04%
```

**开发环境体检**

```console
$ sysx doctor
  ✓ Python         3.11.1 (/usr/bin/python3)
  ✓ git            /usr/bin/git
  ✓ docker         /usr/local/bin/docker
  ✗ tmux           未安装
  ✓ root 权限       当前是 root
  ✓ DNS 解析        example.com → 172.66.147.243
  ✓ 外网连通         可访问 8.8.8.8:53
  ✓ 根分区余量        254.0 GB 可用 (99.2%)

  18/19 项通过
```

**JSON 输出（配合 jq）**

```bash
# 内存占用百分比
sysx mem -j | jq '.percent'

# 找出最占内存的 3 个进程名
sysx proc -j -n 3 -s mem | jq -r '.[].name'

# 列出所有监听端口号
sysx ports -j | jq -r '.[].port'
```

## 选项

| 选项 | 适用命令 | 说明 |
|---|---|---|
| `-j, --json` | 全部 | 以 JSON 格式输出 |
| `-n, --limit N` | `proc` | 显示条数（默认 10） |
| `-s, --sort {cpu,mem}` | `proc` | 排序依据（默认 cpu） |
| `-V, --version` | 全局 | 显示版本号 |
| `-h, --help` | 全局 | 显示帮助 |

## 环境变量

| 变量 | 作用 |
|---|---|
| `NO_COLOR` | 设置后禁用彩色输出（遵循 [no-color.org](https://no-color.org/) 约定） |

## 实现说明

`sysx` 不依赖 `psutil` 等第三方库，直接解析内核暴露的接口：

| 数据 | 来源 |
|---|---|
| 内存 | `/proc/meminfo` |
| 运行时长 | `/proc/uptime` |
| 负载 | `/proc/loadavg` |
| 进程列表 | `/proc/<pid>/stat` |
| CPU 占用率 | 两次采样 `/proc/stat` 计算增量 |
| 磁盘挂载 | `/proc/mounts` + `shutil.disk_usage` |
| 网络接口 | `/sys/class/net/*` |
| DNS | `/etc/resolv.conf` |
| 监听端口 | `/proc/net/tcp`、`/proc/net/tcp6` |

**关于 CPU 占用率**：直接读 `/proc/<pid>/stat` 只能拿到进程的累计 CPU 时间，
除以总和会得出错误结果（长运行进程会被严重高估）。`sysx` 采用两次采样（间隔 250ms）
计算增量占比，结果与 `top` 一致。

**容器环境适配**：在 Docker / Kubernetes 中，`/proc/mounts` 会包含大量 bind mount，
同一块设备重复出现几十次。`sysx` 按设备去重并过滤快照层挂载点，输出干净的磁盘列表。

## 兼容性

| 平台 | 状态 |
|---|---|
| Linux | 完整支持 |
| macOS | 部分支持（无 `/proc`，`info`/`disk`/`doctor` 可用） |
| Windows | 基础支持（`info`/`doctor` 可用） |

## 开发

```bash
# 运行测试套件（46 个用例，纯标准库 unittest）
python3 -m unittest discover -s tests -v

# 严格模式：资源泄漏视为错误
python3 -W error::ResourceWarning -m unittest discover -s tests

# 构建并校验
python3 -m build
python3 -m twine check dist/*      # PyPI 元数据校验
python3 scripts/check_no_deps.py   # 零依赖校验
```

CI 在 Python 3.8 – 3.12 矩阵及 macOS 上自动运行上述检查，
详见 [.github/workflows/test.yml](.github/workflows/test.yml)。

发布到 PyPI 的完整流程见 [PUBLISHING.md](PUBLISHING.md)。

## License

MIT
