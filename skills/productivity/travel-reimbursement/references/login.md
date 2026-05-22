# ERM 登录排错手册

> 主流程见 `SKILL.md` §3，自动化脚本 `scripts/login_erm.sh`。本文是脚本失败时的诊断树。

## 背景：为什么登录必须走浏览器

ERM 登录页的密码被页面 JS **客户端加密**后再 POST。直接用 httpx POST 明文密码必然失败——必须让浏览器执行加密 JS。

## 元素定位方式

脚本通过 `snapshot -i` 获取动态 ref，以 "密码" 标签为锚点：前一个 textbox = 账号（填 `ERM_ACCOUNT`），后一个 textbox = 密码，"登录" 文本的 generic = 提交按钮。不使用 CSS 选择器。

## 结构化错误

登录失败时 stderr 为单行 JSON，含 `error_code`。对照 `references/errors.md`。常见：`wrong_password`、`captcha_required`、`browser_daemon_error`、`snapshot_parse_failed`。

## 诊断树

### 通用：脚本异常时先试重启浏览器

```bash
agent-browser --profile "$PROFILE_DIR" close
```

`PROFILE_DIR` 由脚本从 `ERM_ACCOUNT` 推导为 `$PWD/${ERM_ACCOUNT}/browser-profile`，勿手设。

然后重新运行 `login_erm.sh`。

### 退出码 3：浏览器 daemon / 基础设施

**含脚本开头** `gate_a_try_already_logged_in` 探针：若 `cookies get` 因 daemon 失败，**不会进入填密码流程**。

- 向用户说明内存/daemon 问题
- `agent-browser --profile "$PROFILE_DIR" close` 后重试一次
- 仍失败则**停机**，勿改 ITEMS_JSON 或继续 pipeline

### 退出码 2：snapshot 解析失败

stderr JSON：`error_code=snapshot_parse_failed`。排查：

- 页面未加载完 → 重新运行脚本
- 页面结构变化 → 手动 `snapshot -i` 检查 "密码" / "登录"

### 退出码 1：仍在登录页（gate1 失败）

stderr JSON 由 `classify_login_failure.py` 生成：

1. **`wrong_password`** → 请用户核对 `ERM_ACCOUNT`/`ERM_PASSWORD`。**勿自动重试**
2. **`captcha_required`** → 用户浏览器手动登录一次，再跑 `login_erm.sh`
3. **`login_failed`** → 见 stderr `message`，对照本文

### 退出码 1：cookie probe 未认证（gate2 失败）

URL 已跳转但 probe 返回 `looks_authenticated=false`：

- 查看 stderr 中的 probe JSON，关注 `missing_required_cookie_names`
- Session 可能被另一处抢占 → 停机说明后重跑 login

## 重试策略

**不要在密码错误后自动重试**——避免账号被锁。

## 永远不要做

- 把账号、密码、cookie、token 写进任何文件、日志、模型回复、commit。
- 同时在两个 profile 使用同一个 `ERM_ACCOUNT`。
- 跳过验证直接进 pipeline——Gate.A 会拦截，但已浪费资源。
