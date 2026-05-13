---
name: reimbursement-process-unified
description: 自动处理内网 ERM 通用报销单。适用于根据发票信息创建通用报销单、上传附件、保存单据；agent-browser 以 --profile 模式管理浏览器，负责登录、Cookie 导出、HAR 捕获 dispatch 初始化数据和最终核验。
author: Hermes Agent
version: 2.0
created: 2026-05-06
updated: 2026-05-12
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

- **系统 URL（ERM 基础地址）**：写死在 `scripts/erm_common.py` 的 `ERM_BASE_URL`（当前为 `http://10.83.2.11:8008`）。不向用户收集，不提供环境变量或 CLI 参数覆盖；`run_reimbursement_pipeline.sh` 通过 `PYTHONPATH` 从该模块读取，换主机时只改 `erm_common.py` 一处即可。
- 登录页面：`http://10.83.2.11:8008/portal/app/mockapp/login.jsp?lrid=1`。
- ERM 登录账号和密码：必须由用户提供；不要使用技能中的固定默认账号或历史账号。每次可能是不同用户，AI 需要询问。

## 准备信息

执行前先确认这些输入：
- ERM 登录账号和密码：必须由用户提供；不要使用技能中的固定默认账号或历史账号。
- 发票号码：传给 `--invoice-no`。
- 不含税金额：传给 `--amount`。
- 税额：传给 `--tax-amount`。
- 价税合计金额/报销总额：传给 `--vat-amount`。
- 摘要/用途：传给 `--zy`。
- 收支项目显示名：AI 根据 `--zy` 摘要自动推断（见下方"收支项目推断"章节），推断后向你确认；不确定时提供 2-3 个候选项由你选择。
- 发票类型显示名：传给 `--invoice-type`，通常是 `增值税普通发票` 或 `增值税专用发票`。
- 附件本地路径：如用户要求上传发票或系统强制附件。若用户在本次流程中提供了发票图片/PDF/OFD 等发票材料用于解析，解析完成后必须把原始发票文件作为附件上传（见下方"发票附件上传"章节），不要询问是否需要上传。

不要把账号密码、Cookie、token 写入最终回复、提交记录或持久化文档。命令示例中统一用 `'...'` 占位。

## AI 文件解析行为规范

当用户提供发票文件（图片/PDF/OFD 等）用于解析时，AI 必须遵循以下流程：

1. 先解析文件获取发票信息（发票号、金额、税额等）
2. 解析完成后，**必须自动设置 `ATTACHMENT_FILE` 环境变量**，指向用户提供的原始文件路径
3. 不要询问用户"是否需要上传附件"
4. 然后继续执行报销流程

```bash
# AI 解析完文件后，必须设置此环境变量
export ATTACHMENT_FILE="/workspace/path/to/original-invoice.pdf"

# 然后执行 pipeline
"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" ...
```

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
```

## 收支项目推断

AI 在构造命令前，根据 `--zy` 摘要内容自动推断 `--expense-item`。流程：

1. 读取 `scripts/save_general_reimbursement_from_dispatch.py` 中的 `EXPENSE_ITEM_TO_PK` 字典（68 项），获取完整枚举。
2. 根据 `--zy` 摘要语义匹配最合适的分类。
3. 向用户展示推断结果并确认（例如：`根据摘要"出差北京拜访客户"，推断收支项目为"差旅费"，是否正确？`）。
4. 不确定时提供 2-3 个候选项由用户选择，不要猜测。

注意：
- 脚本 `--expense-item` 的 `choices=` 校验是最终防线；AI 推断值必须精确匹配字典 key。
- 近义名称需格外小心，如"研究与发展费" vs "研究与开发费"、"办公费-其他" vs "其他应收款"。

## 发票附件上传

当用户提供发票图片/PDF/OFD 等材料用于解析发票信息时，解析完成后必须把**同一份原始文件**作为附件随单据一起上传。一张单据只有一个 `accessorybillid`（首次 `generatBillId` 返回的 `pk_bill`），同一个 ID 下可挂载多个附件——`run_reimbursement_pipeline.sh` 已内置「首次生成 → 后续复用」逻辑，AI 不要绕过 pipeline 手动串接上传脚本。

- 单文件：`export ATTACHMENT_FILE='/abs/path/invoice.pdf'`
- 多文件：`export ATTACHMENT_FILES='/abs/path/a.pdf:/abs/path/b.jpg:/abs/path/c.ofd'`（冒号分隔，绝对路径；路径本身禁止包含 `:`）
- 两者同时设置时以 `ATTACHMENT_FILES` 为准。
- 直接复用用户提供的原始路径，不要转换、压缩或重命名。
- 产物：`attachment.json`（首份，兼容旧名）、`attachment_1.json`、`attachment_2.json` …；最终 `accessorybillid` 自动注入保存请求。
- Gate.E：每个文件必须 `ok=true`，且所有上传返回的 `accessorybillid` 必须一致；任一失败立即停机，不要带着缺附件的单据继续保存。
- 不要在最终回复中回显 Cookie、token 等敏感信息。

## 推荐流程（两步）

### 1) 登录（AI 交互式，使用 --profile 模式）

AI 询问用户 ERM 账号和密码（不要询问系统 URL），然后操作浏览器完成登录：

```bash
# Profile 目录：优先使用环境变量，否则默认为技能目录下的 .browser-profile
PROFILE_DIR="${PROFILE_DIR:-${SKILL_DIR}/.browser-profile}"

# 打开登录页（ERM 主机已写死，勿向用户询问 URL）
agent-browser --profile "$PROFILE_DIR" open "http://10.83.2.11:8008/portal/app/mockapp/login.jsp?lrid=1"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# AI 使用 snapshot 获取页面元素引用，根据返回的真实引用（如 @e7、@e8）操作
# snapshot -i 返回示例：{"elements": {"7": {"type": "input", "name": "账号", "ref": "@e7"}, ...}}
SNAPSHOT_OUTPUT=$(agent-browser --profile "$PROFILE_DIR" snapshot -i)
# 根据页面结构，填入用户提供的账号密码（注意：@e<ref> 需替换为实际元素引用）
agent-browser --profile "$PROFILE_DIR" fill @e<账号输入框的实际ref> '<account>'
agent-browser --profile "$PROFILE_DIR" fill @e<密码输入框的实际ref> '<password>'
agent-browser --profile "$PROFILE_DIR" click @e<登录按钮的实际ref>
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# 验证登录成功（页面应跳转，不再包含 login.jsp）
agent-browser --profile "$PROFILE_DIR" get url
```

登录成功后，session 自动保存在 profile 目录中，后续运行可复用。

### 2) 执行单入口脚本

脚本自动完成：登录检查 → Cookie 导出 → 获取 URL → HAR 录制 → 提取默认值 → 保存单据。

```bash
export SKILL_DIR="<actual-skill-directory>"
# Profile 目录：优先使用环境变量，否则默认为技能目录下的 .browser-profile
export PROFILE_DIR="${PROFILE_DIR:-${SKILL_DIR}/.browser-profile}"

"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" \
  --zy '摘要及用途' \
  --amount '116.46' \
  --tax-amount '6.99' \
  --vat-amount '123.45' \
  --expense-item '宣传费' \  # AI 从 EXPENSE_ITEM_TO_PK 推断，推断后需用户确认
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
| `PROFILE_DIR` | 否 | `${SKILL_DIR}/.browser-profile` | agent-browser profile 目录（持久化登录态） |
| `COOKIE` | 否 | 自动从 profile 导出 | 手动指定的 Cookie 头；不设则脚本自动导出 |
| `ATTACHMENT_FILE` | 否 | — | 单附件本地路径 |
| `ATTACHMENT_FILES` | 否 | — | 多附件绝对路径列表，冒号分隔；与 `ATTACHMENT_FILE` 同时设置时优先生效 |
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
