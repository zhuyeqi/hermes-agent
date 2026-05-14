# ERM 登录排错手册

> 主流程见 `SKILL.md`「登录与 workspace」一节；自动化脚本 `scripts/login_erm.sh`。本文是脚本失败时的诊断树。

## 背景：为什么登录必须走浏览器

ERM 登录页的密码被页面 JS **客户端加密**后再 POST。直接用 httpx POST 明文密码必然失败——必须让浏览器执行加密 JS。

## 元素定位方式

脚本通过 `snapshot -i` 获取动态 ref，以 "密码" 标签为锚点：前一个 textbox = 账号，后一个 textbox = 密码，"登录" 文本的 generic = 提交按钮。不使用 CSS 选择器。

## 临时文件与排障

`login_erm.sh` 会在 `${TMPDIR:-/tmp}` 下创建随机目录（`mktemp -d …/erm-login.XXXXXX`），把从浏览器导出的 cookie JSON、probe 输出等只写在该目录内；脚本**正常或异常退出时**会通过 `trap` **整目录删除**，因此排障时不要去找历史上可能存在的固定路径（例如 `/tmp/erm_cookies.json`）。需要保留证据时，应在失败当刻从 stderr 复制输出，或临时改脚本去掉清理逻辑（仅限本地调试，勿提交）。

## 诊断树

### 通用：脚本异常时先试重启浏览器

```bash
agent-browser --profile "$PROFILE_DIR" close
```

然后重新运行 `login_erm.sh`。很多页面加载异常、snapshot 获取失败、元素找不到的问题都能通过重启浏览器解决。

### 退出码 2：snapshot 解析失败

stderr 会输出原始 snapshot。排查：

- 页面未加载完 → 重新运行脚本
- 页面结构变化（iframe、新增元素）→ 手动 `snapshot -i` 检查，确认 "密码" 和 "登录" 文本是否存在

### 退出码 1：仍在登录页（gate1 失败）

1. **密码错误** → 重新运行脚本，输入正确凭证。**不要用错误密码重试**（避免锁号）
2. **图形验证码出现** → 在浏览器里手动登录一次，之后重新运行脚本
3. **页面 JS 未加载完** → 重新运行脚本（脚本会重新 `wait --load networkidle`）

### 退出码 1：cookie probe 未认证（gate2 失败）

URL 已跳转但 probe 返回 `looks_authenticated=false`：

- 查看 stderr 中的 probe JSON，关注 `missing_required_cookie_names`
- 若 `token` 缺失 → 重新运行脚本
- 若全部齐备但仍失败 → Session 被另一处抢占（同账号在别处登录），停机

### pipeline 报 Gate.A：cookie probe 未认证

说明 profile 中会话与 HTTP 探针不一致。先运行 `login_erm.sh` 再跑 `run_reimbursement_pipeline.sh`。确认 `PROFILE_DIR` 与登录脚本使用的是同一目录。

## 重试策略

**不要在密码错误后自动重试**——避免账号被锁。

## 永远不要做

- 把账号、密码、cookie、token 写进任何文件、日志、模型回复、commit。
- 同时在两个 `PROFILE_DIR` 使用同一个 `ERM_ACCOUNT`。
- 跳过验证直接进 pipeline——`run_reimbursement_pipeline.sh` 开头 Gate.A 会拦截无效会话。
