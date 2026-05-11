---
name: reimbursement-process-unified
description: 自动处理内网 ERM 通用报销单。适用于根据发票信息创建通用报销单、上传附件、保存单据；agent-browser 以 --profile 模式管理浏览器，负责登录、Cookie 导出、HAR 捕获 dispatch 初始化数据和最终核验。
author: Hermes Agent
version: 2.0
created: 2026-05-06
updated: 2026-05-11
tags: [finance, reimbursement, internal-system, browser, scripts]
requires:
  - browser
  - python3
  - python-httpx
---

# 通用报销单处理流程

## 目标

用"浏览器 + 脚本"的混合方式创建 ERM 通用报销单，减少纯浏览器点击带来的识别失败。

成功标准：
- 成功登录 ERM，并拿到有效 Cookie。
- 拿到通用报销单新增页面 URL。
- 从新增页的 `/iwebap/evt/dispatch` 响应提取到系统默认字段。
- 如需附件，上传成功并拿到 `accessorybillid`。
- 保存接口返回成功，响应里包含单据主键或可在浏览器中看到保存后的单据。

## 分工原则

优先用脚本做确定性操作：
- 获取通用报销单 URL。
- 解析 Cookie 上下文。
- 从 dispatch 响应提取默认字段。
- 上传附件。
- 构造并提交保存表单。

只在这些场景使用浏览器（agent-browser `--profile` 模式）：
- 登录 ERM（AI 交互式操作，不写入脚本）。
- Cookie 导出：`agent-browser --profile $PROFILE_DIR cookies get`，包含 `HttpOnly` 的 `JSESSIONID` 等。
- HAR 录制：捕获 `/iwebap/evt/dispatch` 响应用于提取默认字段。
- 保存后核验单据状态，或脚本不支持的异常 UI 流程。

不要依赖旧的页面元素 ref。每次浏览器操作前重新观察页面。

## 前置条件

- 系统 URL：当前已验证默认值是 `http://10.83.2.11:8008`。如果用户或运行环境提供了其他 `BASE_URL`，必须原样使用用户/环境提供的值。
- 登录页面：`${BASE_URL}/portal/app/mockapp/login.jsp?lrid=1`。
- ERM 登录账号和密码：必须由用户提供；不要使用技能中的固定默认账号或历史账号。每次可能是不同用户，AI 需要询问。

## 准备信息

执行前先确认这些输入：
- `base_url`：用户或运行环境给出的 ERM 基础地址，必须原样使用；不要自行增加、删除或改写任何路径段。
- ERM 登录账号和密码：必须由用户提供；不要使用技能中的固定默认账号或历史账号。
- 发票号码：传给 `--invoice-no`。
- 不含税金额：传给 `--amount`。
- 税额：传给 `--tax-amount`。
- 价税合计金额/报销总额：传给 `--vat-amount`。
- 摘要/用途：传给 `--zy`。
- 收支项目显示名：传给 `--expense-item`，必须是脚本支持的精确名称。
- 发票类型显示名：传给 `--invoice-type`，通常是 `增值税普通发票` 或 `增值税专用发票`。
- 附件本地路径：如用户要求上传发票或系统强制附件。

不要把账号密码、Cookie、token 写入最终回复、提交记录或持久化文档。命令示例中统一用 `'...'` 占位。

## 脚本位置

本技能自带脚本在 `scripts/`：
- `build_cookie_header.py`：从 cookies JSON（`agent-browser --profile $PROFILE_DIR cookies get` 输出）生成并校验原始 `Cookie` 请求头。
- `merge_set_cookie_header.py`：仅当拿不到 cookie 导出时，用 `/portal/core` response `Set-Cookie` 等合并生成 `Cookie` 请求头（兜底）。
- `probe_cookie_context.py`：检查 Cookie 是否包含 ERM 会话关键字段。
- `get_general_reimbursement_url.py`：调用菜单接口获取通用报销单新增页 URL。
- `extract_dispatch_defaults.py`：从 dispatch 响应提取保存表单必需默认值。
- `upload_reimbursement_attachment.py`：上传附件并返回 `accessorybillid`。
- `save_general_reimbursement_from_dispatch.py`：从 dispatch 默认值和发票字段构造并保存单据。
- `post_save_form.py`：仅用于调试，提交已经构造好的保存表单。
- `run_reimbursement_pipeline.sh`：单入口脚本，自动完成登录检查、Cookie 导出、HAR 录制、单据保存。

运行时用当前技能目录，不要写死本机绝对路径。若执行器没有自动定位技能目录，先让运行环境提供实际技能目录，再赋给 `SKILL_DIR`：

```bash
SKILL_DIR="<actual-skill-directory>"
BASE_URL="<user-or-environment-provided-erm-base-url>"
```

## 推荐流程（两步）

### 1) 登录（AI 交互式，使用 --profile 模式）

AI 询问用户 ERM 账号和密码，然后操作浏览器完成登录：

```bash
PROFILE_DIR="${PROFILE_DIR:-/opt/data/erm-browser-profile}"
BASE_URL="<user-or-environment-provided-erm-base-url>"

# 打开登录页
agent-browser --profile "$PROFILE_DIR" open "${BASE_URL}/portal/app/mockapp/login.jsp?lrid=1"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# AI 使用 snapshot 或 screenshot 观察页面，找到账号和密码输入框
agent-browser --profile "$PROFILE_DIR" snapshot -i
# 根据页面结构，填入用户提供的账号密码
agent-browser --profile "$PROFILE_DIR" fill @e<ref> '<account>'
agent-browser --profile "$PROFILE_DIR" fill @e<ref> '<password>'
agent-browser --profile "$PROFILE_DIR" click @e<ref>
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# 验证登录成功（页面应跳转，不再包含 login.jsp）
agent-browser --profile "$PROFILE_DIR" get url
```

登录成功后，session 自动保存在 profile 目录中，后续运行可复用。

### 2) 执行单入口脚本

脚本自动完成：登录检查 → Cookie 导出 → 获取 URL → HAR 录制 → 提取默认值 → 保存单据。

```bash
export SKILL_DIR="<actual-skill-directory>"
export BASE_URL="<user-or-environment-provided-erm-base-url>"
export PROFILE_DIR="${PROFILE_DIR:-/opt/data/erm-browser-profile}"

"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" \
  --zy '摘要及用途' \
  --amount '116.46' \
  --tax-amount '6.99' \
  --vat-amount '123.45' \
  --expense-item '宣传费' \
  --invoice-type '增值税普通发票' \
  --invoice-no '12345678901234567890'
```

产物文件（当前目录）：
- `menu_url.json`
- `dispatch.json`
- `defaults.json`
- `attachment.json`（有附件时）
- `save_result.json`

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SKILL_DIR` | 是 | — | 技能目录路径 |
| `BASE_URL` | 是 | — | ERM 基础地址 |
| `PROFILE_DIR` | 否 | `/opt/data/erm-browser-profile` | agent-browser profile 目录（持久化登录态） |
| `COOKIE` | 否 | 自动从 profile 导出 | 手动指定的 Cookie 头；不设则脚本自动导出 |
| `ATTACHMENT_FILE` | 否 | — | 附件本地路径 |
| `DRY_RUN` | 否 | `0` | 设为 `1` 仅构造 payload 不提交 |

## 执行契约（Hard Gates，禁止自由发挥）

以下规则是硬门禁。**任意一条不满足就必须停止**，禁止猜测字段、禁止跳步、禁止自动改走纯视觉继续提交。

- **Gate.A（Login）**：脚本打开登录页后 URL 不含 `login.jsp`，说明 session 有效。
- **Gate.B（menu_url.json）**：`menu_url.json` 包含 `result.absolute_url`，且 `success=true`。
- **Gate.C（dispatch.json）**：HAR 中找到 `/iwebap/evt/dispatch` 响应，解析后顶层为对象且包含 `dataTables`。
- **Gate.D（defaults.json）**：必须包含 `head.pk_org_v`、`head.deptid_v`、`head.jsfs`、`head.skyhzh`、`body.defitem13`。
- **Gate.E（attachment）**：如要求附件，必须 `ok=true` 且有 `accessorybillid`。

失败处理规范：
- `dispatch` 只允许一次标准重试。
- 重试仍失败必须停机并输出证据（当前 URL、HAR 条目数）。

## 验证与回归清单（必须执行）

成功路径：
- `dispatch.json` 存在且含 `dataTables`。
- `defaults.json` 关键字段齐全（`pk_org_v/deptid_v/jsfs/skyhzh/defitem13`）。
- `save_result.json`（或 stdout）显示 `ok=true`，并包含单据主键或单据号。
- 浏览器最终核验字段和附件一致。

失败路径：
- `dispatch` 缺失/解析失败：仅重试一次；仍失败停机并输出证据。
- `defaults` 缺字段：回到新增页重抓；禁止猜测字段。
- 附件失败且业务要求附件：必须停机。

## 浏览器兜底边界

- **允许**：登录、最终核验、极少数 UI 异常确认。
- **禁止**：在 `dispatch/defaults` 缺失时继续提交；猜测系统字段；因为下拉框/弹窗问题直接改走纯视觉提交。
