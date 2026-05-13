# ERM 登录排错手册

> 主流程见 `SKILL.md` §2。本文是失败时的诊断树，按顺序排查。

## 背景：为什么登录必须走浏览器

ERM 登录页（`/portal/app/mockapp/login.jsp?lrid=1`）的密码会被页面 JS **客户端加密**后再 POST 到 `/portal/core`。HAR 抓包确认 POST 体里 `password` 字段是经过加密的长十六进制串，并带 `password_encoded` 后缀。**直接用 httpx POST 用户名/明文密码必然失败**——必须让浏览器执行加密 JS。

## 登录表单稳定 selector（从 HAR 反推）

| 元素 | CSS selector |
|---|---|
| 账号输入框 | `#userid` |
| 密码输入框 | `#password` |
| 登录按钮 | `#submitBtn` |
| 报错提示 | `#tiplabel` |
| 语言下拉 | `#multiLanguageCombo` |

这些 ID 来自 ERM Portal 引擎，**不会随会话变化**。优先用 ID 选择器，不要让模型从 `snapshot -i` 的 ref 里猜。

## 诊断树

### 症状 1：`fill '#userid'` 直接报「element not found」

- 检查页面是否真的加载完：
  ```bash
  agent-browser --profile "$PROFILE_DIR" wait '#userid'
  agent-browser --profile "$PROFILE_DIR" get url
  ```
- 如果 URL 不是 `login.jsp`，说明 profile 里已有有效 session，被自动跳过登录页。**这是好事**——直接跑 cookie probe 确认登录有效（见 SKILL.md §2.1），跳过 §2.2。
- 如果 URL 是 `login.jsp` 但找不到 `#userid`：可能页面用了 iframe。`agent-browser snapshot -i` 看一下结构，必要时切到 iframe。

### 症状 2：点 `#submitBtn` 后页面仍是 `login.jsp`

可能原因和处理：

1. **密码错误**：读取 `#tiplabel` 文本：
   ```bash
   agent-browser --profile "$PROFILE_DIR" get text '#tiplabel'
   ```
   有「用户名或密码错误」字样 → 向用户重新索要凭证，不要重试同样的值。

2. **图形验证码出现**：snapshot 里出现 `verifyCode` / 验证码图片元素 → 停机，提示用户在浏览器里手动输入一次，之后用户再触发流程。

3. **页面 JS 还没加载完**：在 click 前补 `wait --load networkidle`，再 click 一次。最多重试 1 次。

### 症状 3：URL 已离开 `login.jsp`，但 cookie probe `looks_authenticated=false`

URL 闸过了不代表登录成功——有些路由会把未登录用户重定向到中间页。

- 重新导出 cookie 后再 probe：
  ```bash
  agent-browser --profile "$PROFILE_DIR" cookies get --json > /tmp/c.json
  python3 "$SKILL_DIR/scripts/build_cookie_header.py" --cookies-json /tmp/c.json
  ```
  关注 `missing_required_cookie_names`：必须包含 `JSESSIONID`、`token`、`user_org`、`pk_unit`、`datasource`、`userid`、`usercode`。
- 若 `token` 缺失 → 重新登录（回到 §2.2）。
- 若全部齐备但 probe 仍 `looks_authenticated=false` → 多半是 Session 被另一处抢占（同账号在别处登录）。停机告知用户。

### 症状 4：probe 调 `/mp/msgtype/list` 拿到非 200 / 非 JSON

- 200 但 content-type 是 `text/html` → 拿到的是登录页，cookie 失效。回到 §2.2。
- 502 / 504 → ERM 后端短暂不可用。等 30s 重试 probe 1 次；仍失败则停机。

## 重试策略上限

| 操作 | 最多重试 | 失败后 |
|---|---|---|
| `wait '#userid'` | 2（每次间隔 networkidle） | 停机 |
| 提交后等待 networkidle | 1 | 检查 `#tiplabel` |
| cookie probe | 1（等 30s） | 停机 |

**不要在密码错误后自动重试**——避免账号被锁。

## 永远不要做

- 把账号、密码、cookie、token 写进任何文件、日志、模型回复、commit。
- 同时在两个 `PROFILE_DIR` 使用同一个 `ERM_ACCOUNT`。
- 跳过 §2.3 验证直接进 pipeline——pipeline 内部 Gate.A 也会拦下来，但消耗的 HAR/dispatch 抓取已经浪费。
