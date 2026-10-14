# Changelog

本项目的所有重要变更都会记录在此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-10-14

### Added（新增）

- `ports` 子命令新增 UDP / UDP6 监听展示（原有 TCP / TCP6 不变）。
- 新增英文版文档 `README.en.md`，中文版 `README.md` 顶部提供语言切换链接。
- 新增 `CHANGELOG.md`（即本文件）。
- 测试套件从 46 个扩充至 **75 个**，覆盖两轮代码审查修复的全部回归点。

### Changed（变更）

- 表格渲染改用显示宽度统计（CJK 字符按双宽计算），中英混排下表头与列宽对齐。
- `net` 子命令表格中的"本机 IP"列更名为"默认出口 IP"，语义更准确。
- 非 Linux 平台上，`ports` / `proc` / `disk` 在无数据时给出明确的平台不支持提示，而非静默空表。

### Fixed（修复）

- IPv6 地址解码：修正 `/proc/net/tcp6` 等内核小端字节序还原错误。
- `/proc` 挂载点路径中的八进制转义（如空格 `\040`）未解码的问题。
- `/etc/os-release` 解析：值内 `\n` / `\t` 转义未还原、续行合并不完整的问题。
- `human_bytes` / `render_bar` 对负值、越界百分比未做钳位的问题。
- 读取不到 `MemTotal` 时 `proc` 的 `mem_percent` 渲染异常。
- 网络接口 `speed` 为异常值（0 或 0xFFFFFFFF）时进入 top 带宽列表的问题。
- 管道场景（如 `sysx info | head`）触发 `BrokenPipeError` 时不再刷栈，静默退出。
- 发布工作流：SHA256 校验和不再生成进 `dist/`，避免 PyPI 发布工具误报 `InvalidDistribution`。

### Removed（移除）

- 清理死代码：`emit` / `set_defaults(func=...)` 间接层、`--debug` 外的空操作分支等。

## [1.0.0] - 2026-10-08

首个正式版本，发布至 PyPI（发行包名 `sysx-cli`，运行命令 `sysx`）。

- 纯 Python 标准库实现，运行时零第三方依赖。
- 9 个子命令：`info` / `mem` / `disk` / `net` / `proc` / `ports` / `env` / `doctor` / `top`。
- 人类可读表格与 `--json` 机器可读输出双模式。
- GitHub Actions 覆盖 Python 3.8 – 3.12 的 Linux / macOS 多平台测试，Release 工作流自动构建 wheel 与 sdist。

[1.1.0]: https://github.com/maoxian3824/sysx/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/maoxian3824/sysx/releases/tag/v1.0.0
