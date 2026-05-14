---
name: travel-reimbursement
description: 创建内网 ERM 差旅费报销单（tradetype=264X-Cxx-CLBX）。脚本负责确定性操作（菜单 URL、dispatch 默认值提取、附件上传、保存提交），agent-browser --profile 负责登录、cookie 导出、HAR 抓 dispatch、最终核验。所有 cookie/明细/附件按 ERM 账号隔离到 ACCOUNT_WORKSPACE。详细字段映射见 reference/items-schema.md，登录排错见 reference/login.md。
author: Hermes Agent
version: 0.3.0
created: 2026-05-13
updated: 2026-05-13
tags: [finance, reimbursement, travel, internal-system, browser]
status: alpha
requires:
  - agent-browser
  - python3
  - python-httpx
---

# 差旅费报销单（ERM）

> 状态：alpha 首版可验证。流程是「登录 → pipeline → 核验」三步，所有产物落在账号专属目录。

ERM 主机地址写死在 `scripts/erm_common.py::ERM_BASE_URL`（当前 `http://10.83.2.11:8008`），不要向用户索取。

## 0. 必备输入

| 项 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `SKILL_DIR` | 是 | — | 当前技能目录绝对路径 |
| `ERM_ACCOUNT` | 是 | — | ERM 账号（用于工作空间隔离） |
| `ACCOUNT_WORKSPACE` | 否 | `$PWD/${ERM_ACCOUNT}` | 账号专属工作空间根目录 |
| `PROFILE_DIR` | 否 | `${ACCOUNT_WORKSPACE}/browser-profile` | 浏览器 profile，持久化 session |
| `ITEMS_JSON` | 是 | — | 明细 JSON，**必须**位于 `ACCOUNT_WORKSPACE` 之内 |
| `ATTACHMENT_FILE(S)` | 否 | — | 附件路径，**必须**位于 `ACCOUNT_WORKSPACE` 之内；多个用 `:` 分隔 |
| `RUN_DIR` | 否 | `${ACCOUNT_WORKSPACE}/runs/travel-<ts>` | 本次运行产物目录 |
| `DRY_RUN` | 否 | `0` | `1` = 只构造 payload 不提交 |

ERM 账号和密码只通过交互向用户索取，**不写入日志、回复、文件、commit**。

## 1. 准备工作空间

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
mkdir -p "$ACCOUNT_WORKSPACE"/{browser-profile,items,attachments,runs}
```

明细 JSON 字段定义见 `reference/items-schema.md`。最小骨架：

```json
{
  "summary": "北京出差",
  "transports": [{"departure_date":"...","arrival_date":"...","vehicle":"火车（二等座）","invoice_form":"火车电子报销凭证","invoice_no":"T1","amount":"500.00"}],
  "hotels": [],
  "subsidies": [{"tool":"火车","official_car_pickup":"否","hosted_by_counterparty":"否"}]
}
```

至少包含 `transports` / `hotels` / `subsidies` 之一。上例中 subsidies 未填 `days`，会按 §1.1 从 transports 日期推算并向你确认。

### 1.1 出差天数推算（subsidies[].days）

当 `subsidies[].days` 未提供时，按以下流程确认：

1. **有 transports**：展示日期范围 `min(departure_date) ~ max(arrival_date)`，请用户确认出差天数。例如：「行程日期范围：2026-05-04 至 2026-05-22，请确认出差天数。」
2. **无 transports**：直接向用户索取 `days`，不推算。
3. **用户已提供 `days`**：跳过推算，使用用户值。

仅对缺少 `days` 的 subsidy 条目执行推算。用户确认后，将 `days` 写入 ITEMS_JSON 再进入 §3 pipeline。脚本中 `days` 仍为 `require` 必填——推算发生在脚本执行之前。

### 1.2 用户提交发票文件时

当用户提供发票文件时，**必须**按顺序执行以下步骤：

1. 用 vision/OCR 解析发票拿到金额、税额、发票号，填入 `ITEMS_JSON`。
2. **立即**执行文件复制（不要只创建目录）：

```bash
_att_dir="${ACCOUNT_WORKSPACE}/attachments/$(date +%Y%m%d)_${TAG}"
mkdir -p "$_att_dir"
cp /path/from/user/invoice.pdf "$_att_dir/"
export ATTACHMENT_FILES="$(find "$_att_dir" -type f | paste -sd ':')"
```

其中 `TAG` 取 `summary` 的简短标识（如 `beijing`），用于区分不同次提交的附件，名称中不含连字符。
3. 不要询问「是否需要上传附件」——发票即附件，直接进 pipeline。
4. 多次提交时每次使用不同的 `TAG`，附件目录仅含本次发票，避免与历史文件混淆。

### 1.3 预检

执行预检脚本，验证所有输入数据齐全后再进入登录：

```bash
bash "${SKILL_DIR}/scripts/preflight_check.sh"
```

退出码 `0` 才进入 §2；失败时按 stderr 提示补全数据后重新执行 §1。

## 2. 登录

ERM 登录页密码由 JS 客户端加密，**不能用脚本直接 POST**，必须走浏览器或者下方的自动化脚本。

### 自动登录脚本

```bash
"$SKILL_DIR/scripts/login_erm.sh"
```

脚本参数：

| 项 | 必填 | 说明             |
|---|---|----------------|
| `SKILL_DIR` | 是 | 当前技能目录绝对路径     |
| `PROFILE_DIR` | 是 | 浏览器 profile 目录 |
| `ERM_USERID` | 否 | 缺失时脚本报错退出，需通过环境变量提供 |
| `ERM_PASSWORD` | 否 | 缺失时脚本报错退出，需通过环境变量提供 |

退出码：`0` = 登录成功（含已登录跳过）；`1` = 登录失败；`2` = 环境缺失或 snapshot 解析失败。

脚本自动完成：探测是否已登录 → 未登录则打开浏览器、`snapshot -i` 解析动态 ref、填写凭证 → 双闸验证（URL 不含 login.jsp + cookie probe 认证）。脚本退出码 0 即表示探测和验证均已通过，无需再额外执行 `probe_cookie_context.py` 等探测验证脚本。凭证**绝不写入文件**，用完立即 `unset`。

### 手动调试（仅在脚本失败时使用）

脚本失败时，参考 `reference/login.md` 按症状走诊断树。**不要在密码错误后自动重试**（避免锁号）。

手动步骤参见 git history 中 §2.1–2.3 的历史版本。

## 3. 执行 pipeline

```bash
export ITEMS_JSON="${ACCOUNT_WORKSPACE}/items/<file>.json"
export ATTACHMENT_FILES="${ACCOUNT_WORKSPACE}/attachments/<dir>/a.pdf:..."  # 可选
export DRY_RUN=0   # 设 1 只构造 payload

"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh"
```

产物全部落在 `$RUN_DIR`：`cdp_cookies.json`、`menu_url.json`、`dispatch.json`、`defaults.json`、`attachment_*.json`、`save_form.json`、`save_result.json`。

## 4. 硬闸（pipeline 内置，失败即停机）

| Gate | 检查 | 失败动作 |
|---|---|---|
| A. login | URL 不含 `login.jsp` 且 cookie probe `looks_authenticated=true` | 回到 §2，最多重试 1 次 |
| B. menu_url | `menu_url.json.result.absolute_url` 存在且 `success=true` | 停机 |
| C. dispatch | HAR 抓到 `/iwebap/evt/dispatch` 且响应含 `dataTables` | 重打开新增页，重试 1 次 |
| D. defaults | head 必填字段齐 + transport/hotel/subsidy 至少一组有字段 | 停机，禁止猜测 |
| E. attachment | 业务要求附件时 `ok=true` 且有 `accessorybillid` | 停机 |
| 隔离 | `ITEMS_JSON` 与 `ATTACHMENT_FILES` 必须在 `ACCOUNT_WORKSPACE` 之下（绝对路径前缀匹配） | 停机 |

成功路径还应满足：
- `save_form.json.bill.head.djlxbm == "264X-Cxx-CLBX"`
- `save_form.json.bill.body.bodys` 含 `arap_bxbusitem` / `other` / `bzitem` 表行
- 补贴 `standard_source ∈ {items, dispatch}`，**绝不可硬编码**
- `save_result.json.ok == true`

## 5. 浏览器边界

- **允许**：登录、cookie 导出、极少数 UI 异常确认。
- **禁止**：dispatch/defaults 缺失时继续提交；猜测系统字段；跨账号共享 cookie/明细/附件；把账号、密码、cookie、token 写入回复、日志、提交记录。

## 引用

- `references/items-schema.md` — 差旅明细 JSON 完整字段映射
- `references/login.md` — 登录异常诊断树（密码错、验证码、Session 抢占、cookie 缺）
- `scripts/run_reimbursement_pipeline.sh` — 单入口 orchestrator（内置 Gate A–E）
- `scripts/probe_cookie_context.py` — Cookie 探针（`--probe-msgtype-list` 用于登录后验证）
- `scripts/erm_common.py` — `ERM_BASE_URL` 唯一来源
- `har/sample_items.json` — 多明细完整示例
