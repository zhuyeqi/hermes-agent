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
  "subsidies": [{"days":2,"tool":"火车","official_car_pickup":"否","hosted_by_counterparty":"否"}]
}
```

至少包含 `transports` / `hotels` / `subsidies` 之一。

## 2. 登录（必须走浏览器）

ERM 登录页密码由 JS 客户端加密，**不能用脚本直接 POST**。仅在浏览器里完成。

登录表单稳定 selector（来自 HAR 反推，不会变化）：

| 元素 | selector |
|---|---|
| 账号 | `#userid` |
| 密码 | `#password` |
| 登录按钮 | `#submitBtn` |

### 2.1 先探测：是否已经登录

```bash
agent-browser --profile "$PROFILE_DIR" cookies get --json > /tmp/erm_cookies.json
COOKIE=$(python3 "$SKILL_DIR/scripts/build_cookie_header.py" \
  --cookies-json /tmp/erm_cookies.json \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['cookie_header'])")

python3 "$SKILL_DIR/scripts/probe_cookie_context.py" \
  --cookie "$COOKIE" --probe-msgtype-list > /tmp/erm_probe.json
cat /tmp/erm_probe.json
```

判定：`/tmp/erm_probe.json` 里 `msgtype_list_probe.looks_authenticated == true` 即已登录 → **直接跳到 §3**。

### 2.2 浏览器登录（仅在 2.1 判定未登录时执行）

向用户索取账号/密码后：

```bash
read -r -s -p "ERM userid: " ERM_USERID; echo
read -r -s -p "ERM password: " ERM_PASSWORD; echo

agent-browser --profile "$PROFILE_DIR" open "http://10.83.2.11:8008/portal/app/mockapp/login.jsp?lrid=1"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle
SNAPSHOT_OUTPUT=$(agent-browser --profile "$PROFILE_DIR" snapshot -i)
agent-browser --profile "$PROFILE_DIR" fill @e<账号输入框的实际ref> '<account>'
agent-browser --profile "$PROFILE_DIR" fill @e<密码输入框的实际ref> '<password>'
agent-browser --profile "$PROFILE_DIR" click @e<登录按钮的实际ref>
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# 验证登录成功（页面应跳转，不再包含 login.jsp）
agent-browser --profile "$PROFILE_DIR" get url

unset ERM_USERID ERM_PASSWORD
```

### 2.3 验证登录（两道闸都要过）

```bash
# 闸 1：URL 闸
URL=$(agent-browser --profile "$PROFILE_DIR" get url)
echo "$URL" | grep -q login.jsp && { echo "still on login page"; exit 1; }

# 闸 2：cookie probe 闸（重跑 2.1）
agent-browser --profile "$PROFILE_DIR" cookies get --json > /tmp/erm_cookies.json
COOKIE=$(python3 "$SKILL_DIR/scripts/build_cookie_header.py" \
  --cookies-json /tmp/erm_cookies.json \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['cookie_header'])")
python3 "$SKILL_DIR/scripts/probe_cookie_context.py" \
  --cookie "$COOKIE" --probe-msgtype-list \
  | python3 -c "import json,sys;d=json.load(sys.stdin);sys.exit(0 if d['msgtype_list_probe']['looks_authenticated'] else 1)"
```

任一闸不过 → 见 `reference/login.md`，按症状走诊断树。**不要在密码错误后自动重试**（避免锁号）。

## 3. 执行 pipeline

```bash
export ITEMS_JSON="${ACCOUNT_WORKSPACE}/items/<file>.json"
export ATTACHMENT_FILES="${ACCOUNT_WORKSPACE}/attachments/<dir>/a.pdf:..."  # 可选
export DRY_RUN=0   # 设 1 只构造 payload

"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh"
```

产物全部落在 `$RUN_DIR`：`cdp_cookies.json`、`menu_url.json`、`dispatch.json`、`defaults.json`、`attachment_*.json`、`save_form.json`、`save_result.json`。

## 4. 用户提交发票文件时

1. 用 vision/OCR 解析发票拿到金额、税额、发票号，填入 `ITEMS_JSON`。
2. **立即**把原始发票文件复制到 `${ACCOUNT_WORKSPACE}/attachments/<date-tag>/` 并 `export ATTACHMENT_FILES=...`。
3. 不要再问用户「是否需要上传附件」——业务上发票就是附件，直接进 §3。

## 5. 硬闸（pipeline 内置，失败即停机）

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

## 6. 浏览器边界

- **允许**：登录、cookie 导出、HAR 抓 dispatch、最终核验、极少数 UI 异常确认。
- **禁止**：dispatch/defaults 缺失时继续提交；猜测系统字段；跨账号共享 cookie/明细/附件；把账号、密码、cookie、token 写入回复、日志、提交记录。

## 引用

- `reference/items-schema.md` — 差旅明细 JSON 完整字段映射
- `reference/login.md` — 登录异常诊断树（密码错、验证码、Session 抢占、cookie 缺）
- `scripts/run_reimbursement_pipeline.sh` — 单入口 orchestrator（内置 Gate A–E）
- `scripts/probe_cookie_context.py` — Cookie 探针（`--probe-msgtype-list` 用于登录后验证）
- `scripts/erm_common.py` — `ERM_BASE_URL` 唯一来源
- `har/sample_items.json` — 多明细完整示例
