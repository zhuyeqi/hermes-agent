---
name: travel-reimbursement
description: 创建内网 ERM 差旅费报销单（tradetype=264X-Cxx-CLBX）。脚本负责确定性操作（菜单 URL、dispatch 默认值、附件上传、保存）；agent-browser --profile 负责登录与最终核验。所有 cookie/明细/附件按 ERM 账号隔离到 $PWD/${ERM_ACCOUNT}。明细字段见 references/items-schema.md，登录排错见 references/login.md。
author: Hermes Agent
version: 1.0
created: 2026-05-13
updated: 2026-05-22
tags: [finance, reimbursement, travel, internal-system, browser, scripts]
requires:
  - browser
  - python3
  - python-httpx
---

# 差旅费报销单（ERM）

## 目标

用「脚本 + 浏览器」混合方式创建 ERM 差旅费报销单（`264X-Cxx-CLBX`）。脚本（`run_reimbursement_pipeline.sh`）封装全部确定性操作；浏览器仅用于登录和最终核验。

## 必备输入

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `SKILL_DIR` | 是 | — | 当前技能目录绝对路径 |
| `ERM_ACCOUNT` | 是 | — | ERM 账号（登录用户名 + 工作空间目录名）；工作空间固定为 `$PWD/${ERM_ACCOUNT}`，profile 为 `$PWD/${ERM_ACCOUNT}/browser-profile`（脚本推导，勿手设） |
| `ERM_PASSWORD` | 登录时 | — | 仅 `login_erm.sh` 需要；跑完后 `unset` |
| `ITEMS_JSON` | 是 | — | 差旅明细 JSON 路径（预检和 pipeline 共用；须在 workspace 内） |
| `DRY_RUN` | 否 | `0` | `1` = 只构造 payload 不提交 |
| `COOKIE` | 否 | 从 profile 导出 | 手动指定时仍须通过 Gate.A 探针 |
| `ATTACHMENT_FILE` | 否 | — | 单附件，须在 workspace 内 |
| `ATTACHMENT_FILES` | 否 | — | 多附件（`:` 分隔），须在 workspace 内；优先于 `ATTACHMENT_FILE` |

ERM 主机地址写死在 `scripts/lib/erm_common.py::ERM_BASE_URL`，不要向用户索取。

ERM 账号（`ERM_ACCOUNT`）与密码（`ERM_PASSWORD`）只通过环境变量传给 `scripts/login_erm.sh`，**不写入日志、回复、文件、commit**。勿设置 `ACCOUNT_WORKSPACE`、`PROFILE_DIR`、`ERM_USERID`。

## 推荐流程

### 0) 准备工作空间与附件

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
mkdir -p "$PWD/${ERM_ACCOUNT}"/{browser-profile,items,attachments,runs}
```

当用户提供发票文件时：

1. 用 vision/OCR 解析发票，填入 `ITEMS_JSON`。
2. 将**原始文件**复制到 `$PWD/${ERM_ACCOUNT}/attachments/<date>_<tag>/`。
3. 设置 `ATTACHMENT_FILES`（绝对路径，须在 workspace 内）。
4. 不要询问「是否需要上传附件」。

```bash
_att_dir="$PWD/${ERM_ACCOUNT}/attachments/$(date +%Y%m%d)_beijing"
mkdir -p "$_att_dir"
cp /path/from/user/invoice.pdf "$_att_dir/"
export ATTACHMENT_FILES="$(find "$_att_dir" -type f | paste -sd ':')"
```

### 1) 构造 ITEMS_JSON

明细 JSON 字段定义见 `references/items-schema.md`。保存到例如 `$PWD/${ERM_ACCOUNT}/items/trip.json`：

```json
{
  "summary": "北京出差",
  "transports": [{"departure_date":"2026-05-04","arrival_date":"2026-05-07","vehicle":"火车（二等座）","invoice_form":"火车电子报销凭证","invoice_no":"T1","amount":"500.00"}],
  "hotels": [],
  "subsidies": [{"days":"2","tool":"火车","official_car_pickup":"否","hosted_by_counterparty":"否"}]
}
```

至少包含 `transports` / `hotels` / `subsidies` 之一。

**枚举字段：** 写入 JSON 前须与 `scripts/lib/erm_travel_enums.py` 的 **key 完全一致**（不是票面简称）。可运行 `validate_travel_items_enums.py --items-json <path>` 或预检 Phase 4b。

**出差天数（`subsidies[].days`）：** 未提供时**必须向用户询问**；有 transports 时仅展示 `min(departure_date) ~ max(arrival_date)` 供参考，**禁止 agent 自行计算或默认填 1**。用户确认后再写入 JSON。

```bash
export ITEMS_JSON="$PWD/${ERM_ACCOUNT}/items/trip.json"
```

### 2) 预检

```bash
bash "${SKILL_DIR}/scripts/preflight_check.sh"
```

预检内容（执行顺序）：
- Phase 1：依赖（python3, agent-browser）
- Phase 2：环境变量（SKILL_DIR, ERM_ACCOUNT, ITEMS_JSON）
- Phase 1c：浏览器 daemon 健康（`check_browser_health.sh`；须已设置 `ERM_ACCOUNT`）
- Phase 1b：httpx 可用（`resolve_python_env.sh` 之后）
- Phase 3：路径隔离（ITEMS_JSON、`ATTACHMENT_FILE` / `ATTACHMENT_FILES` 须在 `$PWD/${ERM_ACCOUNT}` 内）
- Phase 4：ITEMS_JSON 结构与必填字段
- Phase 4b：枚举校验（vehicle、invoice_form、city_type 等）
- Phase 5：附件存在性（有 transport/hotel 明细时须设 `ATTACHMENT_FILE` 或 `ATTACHMENT_FILES`）

退出码 `0` 继续；失败时见 stderr（含 JSON `error_code`），**必读** `references/errors.md`。**预检失败不得跑 login/pipeline。**

### 3) 登录

```bash
export ERM_PASSWORD='<from-user>'
"$SKILL_DIR/scripts/login_erm.sh"
unset ERM_PASSWORD
```

退出码：`0` 已登录或登录成功；`1` 登录失败（stderr JSON）；`2` 环境/快照解析失败；`3` 浏览器 daemon 失败（含开头探针，不进入填密码）。**`wrong_password` 勿自动重试**；**`browser_daemon_error` 须停机并告知用户**。

### 4) 执行 pipeline

```bash
export DRY_RUN=0
"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh"
```

脚本结束会在 stderr 打印 `Artifacts in: <RUN_DIR>`，含 `dispatch.json`、`defaults.json`、`attachment_*.json`（若有）、`save_form.json`、`save_result.json`。

## 附录

### Agent 仅可调用（入口）

1. `scripts/preflight_check.sh`
2. `scripts/login_erm.sh`
3. `scripts/run_reimbursement_pipeline.sh`

### 目录结构

| 路径 | 角色 |
|------|------|
| `scripts/lib/` | 共享层：`init.sh`、`erm_workspace.sh`、`erm_common.py`、`erm_travel_enums.py`、`erm_browser.sh`、`gate_a_session.sh`、`resolve_python_env.sh` |
| `scripts/*.py` | pipeline 内部步骤（勿直接调用） |
| `scripts/archive/` | 维护者调试脚本（非运行时） |

### Hard Gates

- **Gate.A（Session）**：从 profile 导出 Cookie + HTTP 探针（**不**打开 `login.jsp`）。
- **Gate.B**：`menu_url.json` 含 `result.absolute_url`。
- **Gate.C**：dispatch 响应含 `dataTables`（浏览器用 `load` 而非 `networkidle`）。
- **Gate.D**：defaults 含 head 必填 + transport/hotel/subsidy 至少一组。
- **Gate.E**：附件 `ok=true` 且有 `accessorybillid`。
- **隔离**：`ITEMS_JSON` 与 `ATTACHMENT_FILE(S)` 必须在 `$PWD/${ERM_ACCOUNT}` 下。

成功路径：`save_form.json.bill.head.djlxbm == "264X-Cxx-CLBX"`；`save_result.json.ok == true`；补贴 `standard_source ∈ {items, dispatch}`，**不可硬编码**。

### Agent 停机规则（防发散）

| 条件 | 行动 |
|------|------|
| 预检 / `validate_travel_items_enums` 失败 | 只修 JSON 或环境；不 login、不 pipeline |
| `error_code` = `browser_daemon_error` | 告知用户；`agent-browser --profile "$PROFILE_DIR" close`；**停止** |
| `error_code` = `wrong_password` | 请用户核对凭证；**停止**，勿重试 |
| `error_code` = `items_enum_invalid` | 展示 `suggestions`；**停止** |
| 跳过预检直接跑 pipeline | pipeline 入口仍会 enum 预检失败；回到 preflight |

### 浏览器边界

- **允许**：登录、最终核验、极少数 UI 异常确认。
- **禁止**：dispatch/defaults 缺失时继续提交；猜测系统字段；跨账号共享 cookie/明细/附件；把敏感信息写入回复或仓库。

## 引用

- `references/errors.md` — 结构化错误码与停机规则（**必读**）
- `references/items-schema.md` — 差旅明细 JSON 完整字段映射
- `references/login.md` — 登录与 Gate.A 失败诊断
- `scripts/lib/erm_travel_enums.py` — 枚举字典单源
- `scripts/validate_travel_items_enums.py` — 枚举前置校验
- `har/sample_items.json` — 多明细完整示例
