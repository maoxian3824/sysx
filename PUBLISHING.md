# 发布到 PyPI

本文档说明如何把本项目发布到 [PyPI](https://pypi.org/)。

采用 **Trusted Publishing（可信发布）**：通过 OIDC 让 PyPI 直接验证 GitHub Actions 的身份，
**不需要保存任何 API Token 或密码**，是目前官方推荐的方式。

---

## 背景：为什么包名叫 sysx-cli

| 名字 | PyPI 状态 |
|---|---|
| `sysx` | ❌ 已被占用（v0.0.1，2021 年，僵尸包） |
| `systools` | ❌ 已被占用（v0.1.3，2023 年） |
| `systool` | ❌ 已被占用 |
| **`sysx-cli`** | ✅ 可用 |

PyPI 不回收已占用的名字，因此发行包名使用 `sysx-cli`。

**但运行命令仍然是 `sysx`** —— 这两个是解耦的：

```bash
pip install sysx-cli    # 安装用包名
sysx info               # 运行用命令名
```

---

## 前置条件（仅首次需要）

### 1. 注册 PyPI 账号

访问 https://pypi.org/account/register/ 注册。

### 2. 验证邮箱

注册后 PyPI 会发验证邮件，点击链接完成验证。**未验证邮箱无法发布任何包。**

### 3. 开启双因素认证（2FA）

访问 https://pypi.org/manage/account/ ，

在 **Two-factor authentication** 部分开启。推荐用：

- **Authenticator app**（TOTP，如 Google Authenticator / 1Password / Authy）
- 或 **Security key**（硬件密钥）

> ⚠️ PyPI 强制要求发布者开启 2FA，不开启会被拒绝上传。

### 4. 配置 Trusted Publisher

访问 https://pypi.org/manage/account/publishing/ ，

在 **Add a new pending publisher** 表单中填写：

| 字段 | 填入的值 |
|---|---|
| PyPI Project Name | `sysx-cli` |
| Owner | `maoxian3824` |
| Repository name | `sysx` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

> 这是「pending publisher」——项目还不存在时也能配置。
> 第一次成功发布后，它会自动转为正式 publisher。

---

## 发布流程

### 方式一：手动触发（推荐首次使用）

1. 打开 https://github.com/maoxian3824/sysx/actions/workflows/release.yml
2. 点击 **Run workflow**
3. 填写：
   - **tag**：`v1.0.0`
   - **publish_to_pypi**：勾选 ✅
4. 点击 **Run workflow**

工作流会依次执行：

```
运行测试 → 构建 wheel/sdist → 校验零依赖 → twine check
   → 校验版本号与 tag 一致 → 校验包名
   → 创建 GitHub Release
   → 发布到 PyPI（OIDC 鉴权）
```

### 方式二：打 tag 自动发布

```bash
git tag v1.0.0
git push origin v1.0.0
```

> 注意：默认配置下，打 tag 只会创建 GitHub Release，**不会**自动发布到 PyPI。
> 如需打 tag 即发布，修改 `.github/workflows/release.yml` 中 `pypi` job 的 `if` 条件：

```yaml
if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
```

---

## 发布前本地自检

不放心的话，可以完全在本地模拟 PyPI 的检查：

```bash
# 1. 安装构建与校验工具
pip install build twine

# 2. 运行测试
python -m unittest discover -s tests -v

# 3. 构建
python -m build

# 4. 校验元数据（PyPI 会做的检查）
python -m twine check dist/*

# 5. 校验零依赖
python scripts/check_no_deps.py

# 6. 试装验证
python -m venv /tmp/t && /tmp/t/bin/pip install dist/*.whl
/tmp/t/bin/sysx --version
```

### 发布到测试环境（强烈建议首次这样做）

PyPI 版本号**发布后不可覆盖、不可删除**（只能 yank）。
首次发布前建议先发到 TestPyPI 试水：

1. 在 https://test.pypi.org/ 注册账号（与正式 PyPI 账号独立）
2. 同样配置 Trusted Publisher，但 **Environment name 填 `testpypi`**
3. 用官方仓库的测试环境上传：

```bash
python -m twine upload --repository testpypi dist/*
```

4. 从 TestPyPI 安装验证：

```bash
pip install --index-url https://test.pypi.org/simple/ sysx-cli
```

测试通过后再发布到正式 PyPI。

---

## 版本号规则

PyPI **不允许重复使用同一版本号**。发新版本时必须：

1. 修改 `pyproject.toml` 中的 `version`
2. 同步修改 `sysx.py` 中的 `__version__`
3. 更新 `CHANGELOG.md`
4. 打对应的 tag（`v1.0.1`），确保 tag 版本与 pyproject 版本一致

> CI 中有 **版本号一致性检查**，不一致会直接失败。
> 测试 `test_version_matches_module` 会保证两个文件的版本号同步。

---

## 常见问题

### Q: 上传失败，提示 `invalid-publisher` 或 `403 Forbidden`

Trusted Publisher 配置不匹配。逐字核对这五项：

- PyPI Project Name：`sysx-cli`（注意是连字符）
- Owner：`maoxian3824`
- Repository：`sysx`
- Workflow：`release.yml`（必须完全一致，含扩展名）
- Environment：`pypi`（要与 workflow 里 `environment.name` 一致）

### Q: 提示 `File already exists`

该版本号已上传过。PyPI 不允许覆盖，必须递增版本号。

### Q: 提示需要 2FA

去 https://pypi.org/manage/account/ 开启双因素认证。

### Q: 想删掉已发布的版本

PyPI 只能 **yank**（撤回），不能删除。已 yank 的版本 `pip install` 时不会装，
但版本号仍被占用，无法重用。操作入口在项目的 Manage → Releases 页面。

### Q: workflow 里 `id-token: write` 是干什么的

这是 OIDC 必需权限。GitHub 会签发一个短期令牌，PyPI 验证它来确认
「这个请求确实来自 maoxian3824/sysx 仓库的 release.yml 工作流」，
从而不需要长期有效的 API Token。

---

## 发布后

- 包页面：https://pypi.org/project/sysx-cli/
- 安装：`pip install sysx-cli`
- 徽章可加到 README：

```markdown
[![PyPI](https://img.shields.io/pypi/v/sysx-cli.svg)](https://pypi.org/project/sysx-cli/)
[![Downloads](https://img.shields.io/pypi/dm/sysx-cli.svg)](https://pypi.org/project/sysx-cli/)
```
