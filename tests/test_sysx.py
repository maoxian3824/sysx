#!/usr/bin/env python3
"""
sysx 自动化测试套件

使用标准库 unittest 实现，不引入任何第三方测试依赖。
运行方式：

    python3 -m unittest discover -s tests -v
    python3 tests/test_sysx.py
"""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

# 让测试可以直接 import sysx.py
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import sysx  # noqa: E402


SUBCOMMANDS = [
    "info", "mem", "disk", "proc", "net", "env", "ports", "uptime", "doctor",
]


def run_cli(args, expect_ok=True):
    """在子进程中运行 CLI，返回 (returncode, stdout, stderr)。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "sysx.py")] + args,
        capture_output=True, text=True, timeout=60,
    )
    if expect_ok:
        assert proc.returncode == 0, (
            f"命令 {args} 失败，退出码 {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc.returncode, proc.stdout, proc.stderr


def call_main(args):
    """在进程内调用 main()，捕获 stdout。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sysx.main(args)
    return rc, buf.getvalue()


# ------------------------------------------------------------ 工具函数测试

class TestHelpers(unittest.TestCase):
    """human_bytes / human_duration / render_table 等纯函数。"""

    def test_human_bytes_units(self):
        cases = [
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024 ** 2, "1.0 MB"),
            (1024 ** 3, "1.0 GB"),
            (1024 ** 4, "1.0 TB"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(sysx.human_bytes(raw), expected)

    def test_human_bytes_negative_does_not_crash(self):
        # 不保证语义正确，但必须不抛异常
        self.assertIsInstance(sysx.human_bytes(-1), str)

    def test_human_duration(self):
        cases = [
            (0, "0s"),
            (59, "59s"),
            (60, "1m 0s"),
            (3600, "1h 0m 0s"),
            (3661, "1h 1m 1s"),
            (86400, "1d 0h 0m 0s"),
            (90061, "1d 1h 1m 1s"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(sysx.human_duration(raw), expected)

    def test_read_text_missing_file_returns_none(self):
        self.assertIsNone(sysx.read_text("/no/such/file/at/all"))

    def test_render_table_empty_rows(self):
        self.assertEqual(sysx.render_table(["a", "b"], []), "")

    def test_render_table_basic(self):
        out = sysx.render_table(["名称", "值"], [["a", "1"], ["bb", "22"]])
        lines = out.splitlines()
        self.assertEqual(len(lines), 4)  # 表头 + 分隔 + 2 行
        self.assertIn("名称", lines[0])
        # 第二行是分隔线，由连续的 '-' 组成
        self.assertTrue(set(lines[1]) <= {"-", " "},
                        f"分隔行含非分隔字符: {lines[1]!r}")
        self.assertIn("-", lines[1])
        self.assertIn("bb", lines[3])

    def test_render_table_ragged_rows(self):
        # 行长度不足时不应崩溃
        out = sysx.render_table(["a", "b", "c"], [["1"], ["1", "2", "3"]])
        self.assertIn("1", out)

    def test_render_bar_length(self):
        # 关闭颜色后，进度条字符数应等于宽度
        sysx.C.disable()
        bar = sysx.render_bar(50, width=20)
        self.assertEqual(len(bar), 20)
        self.assertEqual(bar.count("█"), 10)

    def test_render_bar_extremes(self):
        sysx.C.disable()
        self.assertEqual(sysx.render_bar(0, 10).count("█"), 0)
        self.assertEqual(sysx.render_bar(100, 10).count("█"), 10)


class TestColorControl(unittest.TestCase):
    """颜色控制与 NO_COLOR 约定。"""

    def tearDown(self):
        # 恢复颜色状态，避免污染其他测试
        sysx.C._enabled = False

    def test_disable_clears_codes(self):
        sysx.C.disable()
        self.assertEqual(sysx.C.RED, "")
        self.assertEqual(sysx.C.RESET, "")

    def test_paint_with_colors_disabled(self):
        sysx.C.disable()
        self.assertEqual(sysx._paint("text", "\033[31m"), "text")


# ------------------------------------------------------------ 子命令测试

class TestSubcommands(unittest.TestCase):
    """每个子命令都应能正常退出且产出输出。"""

    def test_all_subcommands_exit_zero(self):
        for cmd in SUBCOMMANDS:
            with self.subTest(cmd=cmd):
                rc, out, err = run_cli([cmd])
                self.assertEqual(rc, 0)
                self.assertTrue(out.strip(), f"{cmd} 无输出")
                self.assertEqual(err.strip(), "", f"{cmd} 输出到了 stderr: {err}")

    def test_all_subcommands_json_valid(self):
        for cmd in SUBCOMMANDS:
            with self.subTest(cmd=cmd):
                rc, out, err = run_cli([cmd, "-j"])
                self.assertEqual(rc, 0)
                try:
                    parsed = json.loads(out)
                except json.JSONDecodeError as exc:
                    self.fail(f"{cmd} -j 输出非法 JSON: {exc}\n原始输出: {out[:300]}")
                self.assertIsNotNone(parsed)

    def test_proc_limit_option(self):
        rc, out, _ = run_cli(["proc", "-n", "3"])
        self.assertEqual(rc, 0)
        # 表头 2 行 + 分隔 + 最多 3 条数据
        data_lines = [ln for ln in out.splitlines()
                      if ln.strip() and not ln.startswith("PID") and "---" not in ln]
        self.assertLessEqual(len(data_lines), 3)

    def test_proc_sort_by_mem(self):
        rc, out, _ = run_cli(["proc", "-s", "mem", "-n", "5"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.strip())

    def test_proc_json_has_required_keys(self):
        _, out, _ = run_cli(["proc", "-j", "-n", "5"])
        data = json.loads(out)
        self.assertIsInstance(data, list)
        for item in data:
            for key in ("pid", "name", "state", "cpu_percent", "rss", "mem_percent"):
                self.assertIn(key, item)
            self.assertIsInstance(item["pid"], int)
            # CPU 占用率必须在合理区间内
            self.assertGreaterEqual(item["cpu_percent"], 0)
            self.assertLessEqual(item["cpu_percent"], os.cpu_count() * 100)


# ------------------------------------------------------------ 数据结构测试

class TestCollectors(unittest.TestCase):
    """collector 返回的数据结构应稳定。"""

    def test_collect_info_keys(self):
        data = sysx.collect_info(None)
        for key in ("hostname", "os", "kernel", "arch", "cpu", "python",
                    "uptime", "load_average"):
            self.assertIn(key, data)
        self.assertIn("cores", data["cpu"])
        self.assertIn("version", data["python"])

    def test_collect_mem_structure(self):
        data = sysx.collect_mem(None)
        if data is None:
            self.skipTest("当前平台不支持 /proc/meminfo")
        for key in ("total", "used", "free", "available", "percent", "swap"):
            self.assertIn(key, data)
        self.assertGreater(data["total"], 0)
        self.assertGreaterEqual(data["percent"], 0)
        self.assertLessEqual(data["percent"], 100)
        self.assertIn("total", data["swap"])

    def test_collect_disk_no_duplicate_devices(self):
        data = sysx.collect_disk(None)
        devices = [d["device"] for d in data]
        self.assertEqual(len(devices), len(set(devices)),
                         "磁盘列表存在重复设备（容器 bind mount 未去重）")

    def test_collect_disk_sorted_by_percent_desc(self):
        data = sysx.collect_disk(None)
        percents = [d["percent"] for d in data]
        self.assertEqual(percents, sorted(percents, reverse=True))

    def test_collect_uptime(self):
        data = sysx.collect_uptime(None)
        if data["seconds"] is None:
            self.skipTest("当前平台不支持 /proc/uptime")
        self.assertGreater(data["seconds"], 0)
        self.assertIsInstance(data["human"], str)

    def test_collect_ports_structure(self):
        data = sysx.collect_ports(None)
        for item in data:
            self.assertIn("proto", item)
            self.assertIn("port", item)
            self.assertIn(item["proto"], ("tcp", "tcp6"))
            self.assertGreater(item["port"], 0)
            self.assertLessEqual(item["port"], 65535)

    def test_collect_net_structure(self):
        data = sysx.collect_net(None)
        self.assertIn("hostname", data)
        self.assertIn("interfaces", data)
        self.assertIn("dns", data)

    def test_collect_env_returns_dict(self):
        data = sysx.collect_env(None)
        self.assertIsInstance(data, dict)

    def test_collect_doctor_checks(self):
        data = sysx.collect_doctor(None)
        self.assertIsInstance(data, list)
        self.assertTrue(data, "doctor 应至少产出一项检查")
        for item in data:
            self.assertIn("name", item)
            self.assertIn("ok", item)
            self.assertIn("detail", item)
            self.assertIsInstance(item["ok"], bool)

    def test_collect_proc_returns_list(self):
        data = sysx.collect_proc(limit=5, sort_by="cpu")
        self.assertIsInstance(data, list)
        self.assertLessEqual(len(data), 5)


class TestProcStatParsing(unittest.TestCase):
    """进程 stat 解析的边界情况。"""

    def test_read_proc_stat_self(self):
        info = sysx._read_proc_stat(str(os.getpid()))
        self.assertIsNotNone(info, "应能读到当前进程的 stat")
        self.assertIn("name", info)
        self.assertGreaterEqual(info["cpu_ticks"], 0)
        self.assertGreater(info["rss"], 0)

    def test_read_proc_stat_invalid_pid(self):
        self.assertIsNone(sysx._read_proc_stat("999999999"))

    def test_read_total_cpu_ticks(self):
        ticks = sysx._read_total_cpu_ticks()
        if ticks is None:
            self.skipTest("当前平台不支持 /proc/stat")
        self.assertGreater(ticks, 0)

    def test_comm_with_spaces_parsed(self):
        # 构造一个 comm 含空格与右括号的假 stat 文本，验证解析逻辑
        fake = "1234 (my (weird) proc) R " + " ".join(["0"] * 12) + " 42 " + \
               " ".join(["0"] * 8) + " 99 " + " ".join(["0"] * 30)
        with mock.patch.object(sysx, "read_text", return_value=fake):
            info = sysx._read_proc_stat("1234")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "my (weird) proc")
        self.assertEqual(info["state"], "R")


# ------------------------------------------------------------ CLI 行为测试

class TestCliBehavior(unittest.TestCase):
    """帮助、版本、错误处理、退出码。"""

    def test_no_args_shows_help(self):
        rc, out = call_main([])
        self.assertEqual(rc, 0)
        self.assertIn("usage:", out)
        self.assertIn("info", out)

    def test_version_output(self):
        rc, out, _ = run_cli(["--version"])
        self.assertEqual(rc, 0)
        self.assertIn(sysx.__version__, out)

    def test_help_exit_zero(self):
        rc, out, _ = run_cli(["--help"])
        self.assertEqual(rc, 0)
        for cmd in SUBCOMMANDS:
            self.assertIn(cmd, out)

    def test_invalid_subcommand_fails(self):
        rc, out, err = run_cli(["definitely-not-a-command"], expect_ok=False)
        self.assertNotEqual(rc, 0)
        self.assertIn("invalid choice", err)

    def test_invalid_sort_option_fails(self):
        rc, _, err = run_cli(["proc", "-s", "bogus"], expect_ok=False)
        self.assertNotEqual(rc, 0)
        self.assertIn("invalid choice", err)

    def test_subcommand_help_works(self):
        for cmd in SUBCOMMANDS:
            with self.subTest(cmd=cmd):
                rc, out, _ = run_cli([cmd, "--help"])
                self.assertEqual(rc, 0)
                self.assertIn("usage:", out)

    def test_json_flag_documented_in_help(self):
        rc, out, _ = run_cli(["mem", "--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--json", out)


class TestJsonOutputMode(unittest.TestCase):
    """JSON 模式下 stdout 必须是纯净的 JSON（可被 jq 直接消费）。"""

    def test_json_output_is_pure(self):
        for cmd in SUBCOMMANDS:
            with self.subTest(cmd=cmd):
                _, out, _ = run_cli([cmd, "-j"])
                # 非 TTY 环境下不应有 ANSI 转义序列
                self.assertNotIn("\033[", out,
                                 f"{cmd} -j 在非 TTY 下仍输出了颜色转义码")
                json.loads(out)  # 必须能整体解析

    def test_json_pipe_safe_when_tty_flag_set(self):
        # 模拟：即使显式关闭颜色，JSON 依然合法
        buf = io.StringIO()
        sysx.C.disable()
        with redirect_stdout(buf):
            sysx.main(["mem", "-j"])
        json.loads(buf.getvalue())


# ------------------------------------------------------------ 打包元信息测试

class TestPackaging(unittest.TestCase):
    """pyproject.toml 与入口点配置。"""

    def setUp(self):
        path = os.path.join(ROOT, "pyproject.toml")
        if not os.path.exists(path):
            self.skipTest("未找到 pyproject.toml")
        with open(path, "rb") as fh:
            raw = fh.read()
        try:
            import tomllib
            self.meta = tomllib.loads(raw.decode("utf-8"))
        except ImportError:
            self.skipTest("Python < 3.11 无 tomllib")

    def test_project_metadata(self):
        project = self.meta["project"]
        self.assertEqual(project["name"], "sysx")
        self.assertIn("description", project)
        self.assertIn("readme", project)

    def test_no_runtime_dependencies(self):
        # 本项目的核心卖点：零依赖
        self.assertEqual(self.meta["project"].get("dependencies", []), [])

    def test_console_script_entry_point(self):
        scripts = self.meta["project"]["scripts"]
        self.assertEqual(scripts.get("sysx"), "sysx:main")

    def test_version_matches_module(self):
        self.assertEqual(self.meta["project"]["version"], sysx.__version__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
