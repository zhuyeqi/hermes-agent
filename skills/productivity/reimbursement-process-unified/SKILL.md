---
name: reimbursement-process-unified
description: 自动处理内网 ERM 通用报销单。脚本负责确定性操作（菜单 URL、dispatch 默认值、附件上传、保存）；agent-browser --profile 负责登录与最终核验。所有 cookie/附件/运行产物按 ERM 账号隔离到 ACCOUNT_WORKSPACE。登录排错见 references/login.md。
author: Hermes Agent
version: 2.2
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

ERM 主机地址写死在 `scripts/erm_common.py::ERM_BASE_URL`，不要向用户索取。

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

**收支项目推断：** AI 构造 `invoices.json` 前，根据 `--zy` 和发票内容自动推断 `expense_item`：

1. 读取 `scripts/save_general_reimbursement_from_dispatch.py` 中的 `EXPENSE_ITEM_TO_PK`。
2. 对每张发票语义匹配后向用户确认；不确定时给出 2–3 个候选项。
3. 将确认后的 `expense_item` 写入对应条目。值须与字典 key 完全一致。

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
- Phase 2：环境变量（SKILL_DIR, ERM_ACCOUNT, INVOICES_JSON）
- Phase 3：路径隔离（ATTACHMENT_FILE(S) 须在 ACCOUNT_WORKSPACE 内；若设置了附件则 ACCOUNT_WORKSPACE 须已存在）
- Phase 4：发票 JSON 校验（有效 JSON、非空数组、每条含全部必填字段）
- Phase 5：附件文件存在性（无附件时仅 warn）

退出码 `0` 继续；失败时按 stderr 提示修复后重跑。

### 3) 登录

```bash
export ERM_USERID='<from-user>'
export ERM_PASSWORD='<from-user>'
"$SKILL_DIR/scripts/login_erm.sh"
unset ERM_USERID ERM_PASSWORD
```

退出码：`0` 已登录或登录成功；`1` 一般失败；`2` 环境未就绪（必填环境变量缺失、`ERM_BASE_URL` 解析失败）、未通过环境变量提供凭据，或 browser snapshot/refs JSON 解析失败。脚本失败时按 `references/login.md` 诊断。**密码错误不要自动重试**。

### 4) 执行 pipeline

```bash
export DRY_RUN=0
# 发票路径以环境变量 INVOICES_JSON 为准；不要再向本脚本传入 --invoices-json（避免与 argparse 重复参数行为纠缠）。
"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" --zy '摘要及用途'
```

脚本结束会在 stderr 打印 `Artifacts in: <RUN_DIR>`，含 `dispatch.json`、`defaults.json`、`attachment_*.json`（若有）、`save_result.json`。

## 附录

### 脚本

- `scripts/login_erm.sh`：探测已登录 → 浏览器填写凭证 → URL + cookie probe 双闸验证。
- `scripts/run_reimbursement_pipeline.sh`：单入口 orchestrator（Gate.A–E），内部完成 Cookie 解析、URL 获取、dispatch 提取、附件上传、表单保存。产物写入 `RUN_DIR`。
- 其余 `scripts/` 下的 Python 脚本为 pipeline 内部实现，agent 无需直接调用。

### 发票字段与附件上传

- 单文件：`ATTACHMENT_FILE`；多文件：`ATTACHMENT_FILES`（`:` 分隔绝对路径，路径中禁止 `:`）。
- 同时设置时以 `ATTACHMENT_FILES` 为准。
- **路径必须位于 `ACCOUNT_WORKSPACE` 目录下**（pipeline 硬闸）。
- 产物在 `$RUN_DIR`：`attachment.json`（首份别名）、`attachment_1.json`、…
- Gate.E：每个文件 `ok=true`，`accessorybillid` 一致。

### Hard Gates

pipeline 内置检查，失败即停机：

- **Gate.A（Login）**：URL 不含 `login.jsp`，且 cookie probe 确认已认证。
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

## 引用

- `references/login.md` — 登录与 Gate.A 失败诊断
- `scripts/preflight_check.sh` — 预检脚本（依赖、环境变量、路径隔离、发票 JSON、附件）
- `scripts/run_reimbursement_pipeline.sh` — 单入口 orchestrator
- `scripts/login_erm.sh` — 自动登录
- `scripts/erm_common.py` — `ERM_BASE_URL` 唯一来源
