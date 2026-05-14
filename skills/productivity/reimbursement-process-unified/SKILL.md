---
name: reimbursement-process-unified
description: 自动处理内网 ERM 通用报销单。脚本负责确定性操作（菜单 URL、dispatch 默认值、附件上传、保存）；agent-browser --profile 负责登录、Cookie 导出、HAR 捕获 dispatch、最终核验。所有 cookie/附件/运行产物按 ERM 账号隔离到 ACCOUNT_WORKSPACE。登录排错见 references/login.md。
author: Hermes Agent
version: 2.1
created: 2026-05-06
updated: 2026-05-14
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
- 成功登录 ERM，并拿到有效 Cookie（Gate.A：URL + cookie probe 双闸）。
- 拿到通用报销单新增页面 URL。
- 从新增页的 `/iwebap/evt/dispatch` 响应提取到系统默认字段。
- 如需附件，上传成功并拿到 `accessorybillid`（附件路径必须在账号 workspace 内）。
- 保存接口返回成功，响应里包含单据主键或可在浏览器中看到保存后的单据。

## 0. 必备输入

| 项 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `SKILL_DIR` | 是 | — | 当前技能目录绝对路径 |
| `ERM_ACCOUNT` | 是 | — | ERM 账号标识（用于工作空间隔离） |
| `ACCOUNT_WORKSPACE` | 否 | `$PWD/${ERM_ACCOUNT}` | 账号专属工作空间根目录 |
| `PROFILE_DIR` | 否 | `${ACCOUNT_WORKSPACE}/browser-profile` | 浏览器 profile，持久化 session |
| `RUN_DIR` | 否 | `${ACCOUNT_WORKSPACE}/runs/general-<时间戳>` | 本次运行产物目录 |
| `DRY_RUN` | 否 | `0` | `1` = 只构造 payload 不提交 |

ERM 主机地址写死在 `scripts/erm_common.py::ERM_BASE_URL`（当前 `http://10.83.2.11:8008`），不要向用户索取。

ERM 账号和密码只通过环境变量传给 `scripts/login_erm.sh`（`ERM_USERID` / `ERM_PASSWORD`），**不写入日志、回复、文件、commit**。

## 1. 准备工作空间

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
mkdir -p "$ACCOUNT_WORKSPACE"/{browser-profile,attachments,runs}
```

发票解析后，将**原始发票文件**复制到 `${ACCOUNT_WORKSPACE}/attachments/<tag>/` 再设置 `ATTACHMENT_FILE` 或 `ATTACHMENT_FILES`，以满足 pipeline 对路径前缀的硬校验。

## 分工原则

优先用脚本做确定性操作：
- 自动登录与双闸校验：`scripts/login_erm.sh`（与差旅技能同一套 ERM 页面逻辑）。
- 获取通用报销单 URL、解析 Cookie、从 dispatch 提取默认值、上传附件、构造并提交保存表单。

只在这些场景使用浏览器（agent-browser `--profile` 模式）：
- Cookie 导出：`agent-browser --profile $PROFILE_DIR cookies get`。

## 前置条件

- **系统 URL**：见 `scripts/erm_common.py` 的 `ERM_BASE_URL`。不向用户收集。
- **登录页面**：`${ERM_BASE_URL}/portal/app/mockapp/login.jsp?lrid=1`（主机以 `erm_common.py` 为准）。
- ERM 登录账号和密码：必须由用户提供；不要使用技能中的固定默认账号。

## 准备信息

执行前先确认这些输入：
- ERM 登录账号和密码（仅用于设置 `ERM_USERID` / `ERM_PASSWORD` 后调用 `login_erm.sh`）。
- 摘要/用途：`--zy`（整张报销单共用）。
- 发票信息：通过 `--invoices-json` 传入 JSON 文件，每张发票包含：
  - `amount`：不含税金额。
  - `tax_amount`：税额。
  - `vat_amount`：价税合计。
  - `invoice_no`：发票号码。
  - `expense_item`：收支项目显示名（AI 推断，见「收支项目推断」，推断后请用户确认）。
  - `invoice_type`：发票类型（如 `增值税普通发票`）。
- 附件：若需上传，路径须在 `ACCOUNT_WORKSPACE` 下（见 §1）。

不要把账号密码、Cookie、token 写入最终回复、提交记录或持久化文档。命令示例中统一用 `'...'` 占位。

## AI 文件解析行为规范

当用户提供发票文件用于解析时：

1. 先解析文件获取发票信息。
2. 将**原始文件**复制到 `${ACCOUNT_WORKSPACE}/attachments/<date-or-tag>/`。
3. 设置 `export ATTACHMENT_FILE='...'` 或 `ATTACHMENT_FILES`（绝对路径，且在 workspace 内）。
4. 不要询问「是否需要上传附件」。

```bash
export SKILL_DIR="..."
export ERM_ACCOUNT='...'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
cp /path/from/user/invoice.pdf "$ACCOUNT_WORKSPACE/attachments/20260514/invoice.pdf"
export ATTACHMENT_FILE="$ACCOUNT_WORKSPACE/attachments/20260514/invoice.pdf"
```

## 脚本位置

本技能自带脚本在 `scripts/`：
- `login_erm.sh`：探测已登录 → 浏览器填写凭证 → URL + cookie probe 双闸验证。
- `build_cookie_header.py`：从 cookies JSON 生成 `Cookie` 请求头。
- `merge_set_cookie_header.py`：cookie 导出兜底。
- `probe_cookie_context.py`：Cookie 探针（`--probe-msgtype-list` 用于登录后 / Gate.A 验证）。
- `get_general_reimbursement_url.py`：菜单接口取通用报销新增页 URL。
- `extract_dispatch_defaults.py`：从 dispatch 提取保存表单默认值。
- `upload_reimbursement_attachment.py`：上传附件。
- `save_general_reimbursement_from_dispatch.py`：构造并保存单据。
- `post_save_form.py`：调试提交已构造表单。
- `run_reimbursement_pipeline.sh`：单入口（Gate.A–E、产物写入 `RUN_DIR`）。

```bash
export SKILL_DIR="<actual-skill-directory>"
```

## 收支项目推断

AI 在构造 `invoices.json` 前，根据每张发票的 `--zy` 和发票内容自动推断对应的 `expense_item`：

1. 读取 `scripts/save_general_reimbursement_from_dispatch.py` 中的 `EXPENSE_ITEM_TO_PK`。
2. 对每张发票语义匹配后向用户确认；不确定时给出 2–3 个候选项。
3. 将确认后的 `expense_item` 写入 `invoices.json` 对应条目。

每张发票的 `expense_item` 可以不同。`resolve_expense_item_pk` 为最终防线；值须与字典 key 完全一致。

## 发票附件上传

- 单文件：`ATTACHMENT_FILE`
- 多文件：`ATTACHMENT_FILES`（冒号分隔绝对路径；路径中禁止 `:`）
- 同时设置时以 `ATTACHMENT_FILES` 为准。
- **路径必须位于 `ACCOUNT_WORKSPACE` 目录下**（pipeline 硬闸）。
- 产物在 `$RUN_DIR`：`attachment.json`（首份别名）、`attachment_1.json`、…
- Gate.E：每个文件 `ok=true`，`accessorybillid` 一致。

## 推荐流程

### 1) 登录（自动化脚本）

ERM 登录页密码由 JS 加密，不能直接 httpx POST 明文；使用脚本：

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
export ERM_USERID='<from-user>'
export ERM_PASSWORD='<from-user>'
"$SKILL_DIR/scripts/login_erm.sh"
unset ERM_USERID ERM_PASSWORD
```

退出码：`0` 已登录或登录成功；`1` 失败；`2` 环境缺失或 snapshot 解析失败。

脚本失败时按 `references/login.md` 诊断。**密码错误不要自动重试**。

### 2) 执行 pipeline

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
# 可选：export ATTACHMENT_FILE=... 或 ATTACHMENT_FILES=...
export DRY_RUN=0

# AI 生成 invoices.json（以下为示例）
cat > "$ACCOUNT_WORKSPACE/runs/invoices.json" << 'EOF'
[
  {"amount":"60","tax_amount":"6","vat_amount":"66","invoice_no":"147258369","expense_item":"党建工作经费","invoice_type":"增值税普通发票"},
  {"amount":"90","tax_amount":"9","vat_amount":"99","invoice_no":"258369147","expense_item":"办公费-办公用品","invoice_type":"增值税普通发票"}
]
EOF

"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" \
  --zy '摘要及用途' \
  --invoices-json "$ACCOUNT_WORKSPACE/runs/invoices.json"
```

脚本结束会在 stderr 打印 `Artifacts in: <RUN_DIR>`。该目录内含：
- `cdp_cookies.json`（若脚本从 profile 导出 cookie）
- `menu_url.json`、`dispatch.json`、`defaults.json`
- `attachment_*.json`（若有）
- `save_result.json`

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SKILL_DIR` | 是 | — | 技能目录 |
| `ERM_ACCOUNT` | 是 | — | 账号隔离标识 |
| `ACCOUNT_WORKSPACE` | 否 | `$PWD/${ERM_ACCOUNT}` | 工作空间根 |
| `PROFILE_DIR` | 否 | `${ACCOUNT_WORKSPACE}/browser-profile` | agent-browser profile |
| `RUN_DIR` | 否 | `.../runs/general-<ts>` | 产物目录 |
| `COOKIE` | 否 | 从 profile 导出 | 手动指定时仍须通过 Gate.A 探针 |
| `ATTACHMENT_FILE` | 否 | — | 单附件，须在 workspace 内 |
| `ATTACHMENT_FILES` | 否 | — | 多附件，须在 workspace 内 |
| `DRY_RUN` | 否 | `0` | `1` 仅 dry-run |

## 执行契约（Hard Gates）

- **Gate.A（Login）**：打开登录页后 URL 不含 `login.jsp`，且 `probe_cookie_context.py --probe-msgtype-list` 的 `looks_authenticated=true`。
- **Gate.B**：`menu_url.json` 含 `result.absolute_url` 且成功语义满足脚本校验。
- **Gate.C**：HAR 中 `/iwebap/evt/dispatch` 响应体含 `dataTables`。
- **Gate.D**：`defaults` 含 `head.pk_org_v`、`head.deptid_v`、`head.jsfs`、`head.skyhzh`、`body.defitem13`。
- **Gate.E**：附件要求满足时 `ok=true` 且有 `accessorybillid`。
- **隔离**：`ATTACHMENT_FILE(S)` 必须在 `ACCOUNT_WORKSPACE` 下（绝对路径前缀匹配）。

失败处理：`dispatch` 仅允许一次标准重试（与既有约定一致）；重试仍失败须停机并输出证据。

## 验证与回归清单

成功路径：`dispatch.json` 含 `dataTables`；`defaults.json` 关键字段齐全；`save_result.json` 中 `ok=true`；浏览器核验与附件一致。

## 浏览器兜底边界

- **允许**：登录、核验、极少数 UI 异常确认。
- **禁止**：dispatch/defaults 缺失时继续提交；猜测系统字段；**跨账号共享 cookie、附件或 profile**；把敏感信息写入回复或仓库。

## 引用

- `references/login.md` — 登录与 Gate.A 失败诊断
- `scripts/run_reimbursement_pipeline.sh` — 单入口 orchestrator
- `scripts/login_erm.sh` — 自动登录
- `scripts/probe_cookie_context.py` — Cookie 探针
- `scripts/erm_common.py` — `ERM_BASE_URL` 唯一来源