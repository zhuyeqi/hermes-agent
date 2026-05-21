---
name: reimbursement-process-unified
description: 自动处理内网 ERM 通用报销单。脚本负责确定性操作（菜单 URL、dispatch 默认值、附件上传、保存）；agent-browser --profile 负责登录与最终核验。所有 cookie/附件/运行产物按 ERM 账号隔离到 ACCOUNT_WORKSPACE。登录排错见 references/login.md。
author: Hermes Agent
version: 2.4
created: 2026-05-06
updated: 2026-05-21
tags: [finance, reimbursement, internal-system, browser, scripts]
requires:
  - browser
  - python3
  - python-httpx
---

# 通用报销单处理流程

## 目标

用「脚本 + 浏览器」混合方式创建 ERM 通用报销单。脚本（`run_reimbursement_pipeline.sh`）封装全部确定性操作；浏览器仅用于登录和最终核验。

## 必备输入

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `SKILL_DIR` | 是 | — | 当前技能目录绝对路径 |
| `ERM_ACCOUNT` | 是 | — | ERM 账号标识（用于工作空间隔离） |
| `ACCOUNT_WORKSPACE` | 否 | `$PWD/${ERM_ACCOUNT}` | 账号专属工作空间根目录 |
| `PROFILE_DIR` | 否 | `${ACCOUNT_WORKSPACE}/browser-profile` | 浏览器 profile，持久化 session |
| `RUN_DIR` | 否 | `${ACCOUNT_WORKSPACE}/runs/general-<ts>` | 本次运行产物目录 |
| `INVOICES_JSON` | 是 | — | 发票 JSON 路径（预检和 pipeline 共用） |
| `DRY_RUN` | 否 | `0` | `1` = 只构造 payload 不提交 |
| `COOKIE` | 否 | 从 profile 导出 | 手动指定时仍须通过 Gate.A 探针 |
| `ATTACHMENT_FILE` | 否 | — | 单附件，须在 workspace 内 |
| `ATTACHMENT_FILES` | 否 | — | 多附件（`:` 分隔），须在 workspace 内；优先于 `ATTACHMENT_FILE` |

ERM 主机地址写死在 `scripts/lib/erm_common.py::ERM_BASE_URL`，不要向用户索取。

ERM 账号和密码只通过环境变量传给 `scripts/login_erm.sh`（`ERM_USERID` / `ERM_PASSWORD`），**不写入日志、回复、文件、commit**。

## 推荐流程

### 0) 准备工作空间与附件

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
mkdir -p "$ACCOUNT_WORKSPACE"/{browser-profile,attachments,runs}
```

当用户提供发票文件时：

1. 先解析文件获取发票信息。
2. 将**原始文件**复制到 `${ACCOUNT_WORKSPACE}/attachments/<date-or-tag>/`。
3. 设置 `ATTACHMENT_FILE` 或 `ATTACHMENT_FILES`（绝对路径，须在 workspace 内）。
4. 不要询问「是否需要上传附件」。

```bash
cp /path/from/user/invoice.pdf "$ACCOUNT_WORKSPACE/attachments/20260514/invoice.pdf"
export ATTACHMENT_FILE="$ACCOUNT_WORKSPACE/attachments/20260514/invoice.pdf"
```

### 1) 构造发票数据

收集摘要/用途（`--zy`，整张报销单共用），然后构造发票 JSON。

发票 JSON（`$ACCOUNT_WORKSPACE/runs/invoices.json`）为数组，每张发票包含：

| 字段 | 说明 |
|------|------|
| `amount` | 不含税金额 |
| `tax_amount` | 税额 |
| `vat_amount` | 价税合计 |
| `invoice_no` | 发票号码 |
| `expense_item` | 收支项目显示名（见下方推断规则） |
| `invoice_type` | 发票类型（如 `增值税普通发票`） |

**收支项目 / 发票类型（枚举）：** 解析发票后、写入 `invoices.json` 前：

1. 运行 `preflight_check.sh`（Phase 4b）或 `validate_invoice_enums.py --invoices-json <path>` — **唯一**枚举校验入口。
2. 字典唯一定义在 `scripts/lib/erm_enums.py`；`expense_item` / `invoice_type` 须与其中 **key 完全一致**（不是票面简称；「普票」等别名会失败并提示改为 `增值税普通发票`）。
3. `run_reimbursement_pipeline.sh` 启动时再次跑枚举预检；`save_general_reimbursement_from_dispatch.py` **不再**做枚举校验，仅做 PK 映射。
4. 预检报 `invoice_enum_invalid` 时，用 stderr 的 `suggestions` / `allowed_*` 向用户确认后改 JSON，**禁止**擅自选最接近项继续。

```bash
cat > "$ACCOUNT_WORKSPACE/runs/invoices.json" << 'EOF'
[
  {"amount":"60","tax_amount":"6","vat_amount":"66","invoice_no":"147258369","expense_item":"党建工作经费","invoice_type":"增值税普通发票"}
]
EOF
export INVOICES_JSON="$ACCOUNT_WORKSPACE/runs/invoices.json"
```

### 2) 预检

```bash
bash "${SKILL_DIR}/scripts/preflight_check.sh"
```

预检内容：
- Phase 1：依赖检查（python3, agent-browser）
- Phase 1c：浏览器 daemon 健康（`check_browser_health.sh`）
- Phase 2：环境变量（SKILL_DIR, ERM_ACCOUNT, INVOICES_JSON）
- Phase 3：路径隔离（ATTACHMENT_FILE(S) 须在 ACCOUNT_WORKSPACE 内；若设置了附件则 ACCOUNT_WORKSPACE 须已存在）
- Phase 4：发票 JSON 校验（有效 JSON、非空数组、每条含全部必填字段）
- Phase 4b：枚举校验（`expense_item` / `invoice_type` 与系统字典一致）
- Phase 5：附件文件存在性（无附件时仅 warn）

退出码 `0` 继续；失败时 stderr 含 JSON `error_code`，见 `references/errors.md`。**预检失败不得跑 login/pipeline。**

### 3) 登录

```bash
export ERM_USERID='<from-user>'
export ERM_PASSWORD='<from-user>'
"$SKILL_DIR/scripts/login_erm.sh"
unset ERM_USERID ERM_PASSWORD
```

退出码：`0` 已登录或登录成功；`1` 登录失败（stderr JSON，常见 `error_code`: `wrong_password`）；`2` 环境/快照解析失败；`3` 浏览器 daemon/基础设施失败（**含开头** `gate_a_try_already_logged_in` 探针失败，不会进入填密码流程）。脚本失败时读 stderr 的 `error_code`，并对照 `references/errors.md` 与 `references/login.md`。**`wrong_password` 勿自动重试**；**`browser_daemon_error` 须停机并告知用户**。

### 4) 执行 pipeline

```bash
export DRY_RUN=0
# 发票路径以环境变量 INVOICES_JSON 为准；不要再向本脚本传入 --invoices-json（避免与 argparse 重复参数行为纠缠）。
"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" --zy '摘要及用途'
```

脚本结束会在 stderr 打印 `Artifacts in: <RUN_DIR>`，含 `dispatch.json`、`defaults.json`、`attachment_*.json`（若有）、`save_result.json`。

## 附录

### Agent 仅可调用（入口）

1. `scripts/preflight_check.sh`
2. `scripts/login_erm.sh`
3. `scripts/run_reimbursement_pipeline.sh`

### 目录结构

| 路径 | 角色 |
|------|------|
| `scripts/lib/` | 共享层：`init.sh`、`erm_common.py`、`erm_enums.py`、`erm_browser.sh`、`gate_a_session.sh`、`resolve_python_env.sh` |
| `scripts/*.py` | pipeline 内部步骤（勿直接调用） |
| `scripts/archive/` | 维护者调试脚本（非运行时） |

- `login_erm.sh`：已登录则 `gate_a_try_already_logged_in` HTTP 探针短路；daemon 失败 exit 3；否则浏览器登录 + `gate_a_session` 验证。
- `run_reimbursement_pipeline.sh`：Gate.A–E；内部调用 `lib/` 与 Python 步骤。

### 发票字段与附件上传

- 单文件：`ATTACHMENT_FILE`；多文件：`ATTACHMENT_FILES`（`:` 分隔绝对路径，路径中禁止 `:`）。
- 同时设置时以 `ATTACHMENT_FILES` 为准。
- **路径必须位于 `ACCOUNT_WORKSPACE` 目录下**（pipeline 硬闸）。
- 产物在 `$RUN_DIR`：`attachment.json`（首份别名）、`attachment_1.json`、…
- Gate.E：每个文件 `ok=true`，`accessorybillid` 一致。

### Hard Gates

pipeline 内置检查，失败即停机：

- **Gate.A（Session）**：从 profile 导出 Cookie + HTTP `probe_cookie_context` 确认已认证（**不**打开 `login.jsp`，避免 `networkidle` 拖死 daemon）。
- **Gate.B**：`menu_url.json` 含 `result.absolute_url`。
- **Gate.C**：`/iwebap/evt/dispatch` 响应体含 `dataTables`。
- **Gate.D**：`defaults` 含 `head.pk_org_v`、`head.deptid_v`、`head.jsfs`、`head.skyhzh`、`body.defitem13`。
- **Gate.E**：附件上传 `ok=true` 且有 `accessorybillid`。
- **隔离**：`ATTACHMENT_FILE(S)` 必须在 `ACCOUNT_WORKSPACE` 下。

成功路径：`dispatch.json` 含 `dataTables`；`defaults.json` 关键字段齐全；`save_result.json` 中 `ok=true`。

`dispatch` 仅允许一次标准重试；重试仍失败须停机并输出证据。

### 浏览器边界

- **允许**：登录、最终核验、极少数 UI 异常确认。
- **禁止**：dispatch/defaults 缺失时继续提交；猜测系统字段；**跨账号共享 cookie、附件或 profile**；把敏感信息写入回复或仓库。

### Agent 停机规则（防发散）

| 条件 | 行动 |
|------|------|
| 预检 / `validate_invoice_enums` 失败 | 只修 JSON 或环境；不 login、不 pipeline |
| `error_code` = `browser_daemon_error` | 告知用户重启/释放内存；`agent-browser --profile "$PROFILE_DIR" close`；**停止任务** |
| `error_code` = `wrong_password` | 请用户核对账号密码；**停止**，勿重试 |
| `error_code` = `invoice_enum_invalid` | 展示 `suggestions` 请用户确认枚举；**停止** |
| 跳过预检直接跑 pipeline | pipeline 入口仍会 enum 预检失败；回到 preflight 修 JSON |

## 引用

- `references/errors.md` — 结构化错误码与停机规则（**必读**）
- `references/login.md` — 登录与 Gate.A 失败诊断
- `scripts/preflight_check.sh` — 预检脚本（依赖、环境变量、路径隔离、发票 JSON、附件）
- `scripts/run_reimbursement_pipeline.sh` — 单入口 orchestrator
- `scripts/login_erm.sh` — 自动登录
- `scripts/lib/erm_enums.py` — 发票类型/收支项目字典
- `scripts/lib/gate_a_session.sh` — Gate.A cookie + HTTP 探针
- `scripts/validate_invoice_enums.py` — 枚举前置校验
- `scripts/check_browser_health.sh` — daemon 探测（经 `erm_browser_run`）
