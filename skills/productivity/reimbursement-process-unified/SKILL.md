---
name: reimbursement-process-unified
description: 自动处理内网 ERM 通用报销单。适用于根据发票信息创建通用报销单、上传附件、保存单据；优先用脚本调用 ERM 接口，浏览器经 CDP 负责登录与同会话 Cookie 导出（本地 `agent-browser --cdp 9222 cookies get`）、捕获 dispatch 初始化数据和最终核验。
author: Hermes Agent
version: 1.2
created: 2026-05-06
updated: 2026-05-09
tags: [finance, reimbursement, internal-system, browser, scripts]
requires:
  - browser
  - python3
  - python-httpx
---

# 通用报销单处理流程

## 目标

用“浏览器 + 脚本”的混合方式创建 ERM 通用报销单，减少纯浏览器点击带来的识别失败。

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

只在这些场景使用浏览器：
- 登录 ERM。
- **同一 CDP 连接上**完成导航、登录与后续页面操作；不要混用“无 CDP 的本地会话”和“另起的抓包/复制流程”去拼 Cookie。
- 登录成功后，用 **CDP 整 jar 导出 Cookie**（见下一节，本地命令：`agent-browser --cdp 9222 cookies get`），包含 `HttpOnly` 的 `JSESSIONID` 等；不要用 `document.cookie` 或任何只能看到非 HttpOnly 的接口作为最终来源。
- 需要网络证据时，可在同一 CDP 会话上开启请求/响应日志，捕获 `/iwebap/evt/dispatch` 等；**获取 Cookie 本身不依赖**手工复制 `/portal/core` 的 `Set-Cookie` 或 `/mp/msgtype/list` 的 Request `Cookie`（这些仅作无法导出 CDP cookie 时的兜底）。
- 可选：在拿到 `Cookie` 请求头后，用 `probe_cookie_context.py --probe-msgtype-list` 走一次 `${BASE_URL}/mp/msgtype/list` 做会话校验（脚本请求），不是为“从该请求偷 Cookie”。
- 打开通用报销单新增页，等待页面初始化，并捕获最新 `/iwebap/evt/dispatch` 响应。
- 保存后核验单据状态，或脚本不支持的异常 UI 流程。

不要依赖旧的页面元素 ref。每次浏览器操作前重新观察页面。

## 前置条件

- 系统 URL：当前已验证默认值是 `http://10.83.2.11:8008`。如果用户或运行环境提供了其他 `BASE_URL`，必须原样使用用户/环境提供的值。
- 登录页面：`${BASE_URL}/portal/app/mockapp/login.jsp?lrid=1`。
- ERM 登录账号和密码：必须由用户提供；不要使用技能中的固定默认账号或历史账号。

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
- `build_cookie_header.py`：**首选**从 CDP cookies JSON（例如本地 `agent-browser --cdp 9222 cookies get` 输出，形如 `{"cookies":[...]}`）或 Playwright `storage_state` 生成并校验原始 `Cookie` 请求头。
- `merge_set_cookie_header.py`：仅当拿不到 CDP/Playwright 级 cookie 导出时，用 `/portal/core` response `Set-Cookie` 等合并生成 `Cookie` 请求头（兜底）。
- `probe_cookie_context.py`：检查 Cookie 是否包含 ERM 会话关键字段。
- `get_general_reimbursement_url.py`：调用菜单接口获取通用报销单新增页 URL。
- `extract_dispatch_defaults.py`：从 dispatch 响应提取保存表单必需默认值。
- `upload_reimbursement_attachment.py`：上传附件并返回 `accessorybillid`。
- `save_general_reimbursement_from_dispatch.py`：从 dispatch 默认值和发票字段构造并保存单据。
- `post_save_form.py`：仅用于调试，提交已经构造好的保存表单。

运行时用当前技能目录，不要写死本机绝对路径。若执行器没有自动定位技能目录，先让运行环境提供实际技能目录，再赋给 `SKILL_DIR`：

```bash
SKILL_DIR="<actual-skill-directory>"
BASE_URL="<user-or-environment-provided-erm-base-url>"
python3 "$SKILL_DIR/scripts/probe_cookie_context.py" --help
```

## 推荐流程

### 1. 登录并获取完整 Cookie

硬性规则：
- 不要用 `curl`、`httpx`、`requests`、脚本直连 `/mp/msgtype/list` 来“获取登录 Cookie”。这些请求没有浏览器登录态，通常拿不到 `token`。
- `curl` 只能在已经拿到完整 `Cookie` 后用于接口验证；不能用于代替浏览器登录。
- 不要手写、猜测或拼接 `token`、`JSESSIONID`。
- **Cookie 权威来源**：与登录同一浏览器、同一 CDP 连接上的 **完整 cookie jar**（本地 `agent-browser --cdp 9222 cookies get` 或等价的 Playwright `storage_state` / 工具链保证含 HttpOnly 的导出）。不要用 `document.cookie`、不要用只能列出非 HttpOnly 的简化 API 作为最终 `Cookie` 请求头。

**推荐路径（默认按此执行）**

1. 确保自动化使用的是 **CDP 附着的会话**（你本地固定方式：`agent-browser --cdp 9222 ...`，且登录与取 Cookie 必须在同一连接链路）。
2. 打开登录页面：`${BASE_URL}/portal/app/mockapp/login.jsp?lrid=1`。不要自行改写 `BASE_URL`。
3. 使用用户提供的 ERM 账号和密码完成登录。
4. 登录流程走完后 **立即**在同一 CDP 连接上导出 cookies：

```bash
agent-browser --cdp 9222 cookies get > cdp_cookies.json
```

`cdp_cookies.json` 需包含可被 `build_cookie_header.py --cookies-json` 直接消费的 cookies 结构（通常为 `{"cookies":[...]}`）。
5. 生成原始 `Cookie` 请求头（可按需加 `--domain-filter`，仅当 jar 里混入其它站 cookie 时再收紧）：

```bash
python3 "$SKILL_DIR/scripts/build_cookie_header.py" \
  --cookies-json cdp_cookies.json
```

输出中的 `cookie_header` 作为后续脚本的 `--cookie`。若 `missing_required_cookie_names` 非空，不要继续保存单据。

6. 校验 Cookie（推荐带 HTTP 探活）：

```bash
python3 "$SKILL_DIR/scripts/probe_cookie_context.py" \
  --base-url "$BASE_URL" \
  --cookie '...' \
  --probe-msgtype-list
```

通过标准：
- `has_token` 是 `true`。
- `has_jsessionid` 是 `true`。
- `user_org(pk_org_candidate)` 有值。
- `pk_unit(pk_group_candidate)` 或 `pk_group` 有值。
- `missing_required_cookie_names` 是空数组。
- `msgtype_list_probe.looks_authenticated` 是 `true`。

排错要点：
- 若缺 `JSESSIONID`：几乎总是 **未走 CDP 全 jar**（误用 `document.cookie` 或半套 Cookie API）。回到步骤 4 用 `agent-browser --cdp 9222 cookies get` 重导。
- 若缺 `token` 或业务 cookie 不全：通常是 **登录尚未完成**或 **导出过早**（例如 `/portal/core` 尚未写完 cookie）。等待登录后首页/菜单稳定再执行 `agent-browser --cdp 9222 cookies get`；仍缺则重新登录后再导出一次。
- 若 `has_token` 为真但组织/单位类字段仍缺：多为会话初始化未完成，重复步骤 3–5；仍失败再考虑下方兜底（勿先猜字段）。

**兜底（仅当 CDP `getAllCookies` / Playwright 级导出确实不可用时，按顺序尝试）**

1. `agent-browser state save …` 或 `agent-browser --json cookies`（须确认与登录为**同一会话**且导出含 HttpOnly），再 `build_cookie_header.py --cookies-json …`。
2. 捕获 `/portal/core` response `Set-Cookie`，用 `merge_set_cookie_header.py`（可先 `--base-cookie` 合并登录前请求头）：
```bash
python3 "$SKILL_DIR/scripts/merge_set_cookie_header.py" \
  --headers-json portal_core_response_headers.json
# 可选：python3 "$SKILL_DIR/scripts/merge_set_cookie_header.py" --base-cookie '...' --headers-json portal_core_response_headers.json
```
3. 让用户从 DevTools 复制 **authenticated** 请求的完整 `Cookie` 请求头（例如 `/mp/msgtype/list` 已返回 JSON 的那条）。
4. 仍无法凑齐必选 cookie 名称：停止流程并说明缺失项；不要改用 `curl` 伪造登录或用猜测值补缺。

### 2. 用脚本获取通用报销单 URL

```bash
python3 "$SKILL_DIR/scripts/get_general_reimbursement_url.py" \
  --base-url "$BASE_URL" \
  --cookie '...' \
  > menu_url.json
```

通过标准：
- 输出 `result.absolute_url`。
- `response.success` 为真。

然后在浏览器打开 `result.absolute_url`。

### 3. 浏览器捕获 dispatch 响应

打开通用报销单新增页后，等待页面加载完成。捕获最新 URL 包含 `/iwebap/evt/dispatch` 的响应 body，保存为 `dispatch.json`。

如果浏览器工具只能导出网络 JSONL，也可以保存 JSONL，下一步使用 `--observed-jsonl`。

不要手工编造 dispatch 字段。`pk_org_v`、`deptid_v`、`jsfs`、`skyhzh`、`zyx18`、`zyx20`、`defitem13` 等字段必须来自当前会话的 dispatch 响应，除非用户明确给出覆盖值。

### 4. 提取 dispatch 默认值

普通路径：

```bash
python3 "$SKILL_DIR/scripts/extract_dispatch_defaults.py" \
  --dispatch-json dispatch.json \
  > defaults.json
```

JSONL 路径：

```bash
python3 "$SKILL_DIR/scripts/extract_dispatch_defaults.py" \
  --observed-jsonl observed.jsonl \
  > defaults.json
```

通过标准：
- `defaults.head.pk_org_v` 有值。
- `defaults.head.deptid` 和 `defaults.head.deptid_v` 有值。
- `defaults.head.jsfs` 和 `defaults.head.skyhzh` 有值。
- `defaults.body.defitem13` 有值。

如果缺字段，刷新新增页并重新捕获 dispatch；不要猜测这些值。

### 5. 上传附件（需要时）

如果有发票图片、PDF 或系统要求附件，先上传附件：

```bash
python3 "$SKILL_DIR/scripts/upload_reimbursement_attachment.py" \
  --base-url "$BASE_URL" \
  --cookie '...' \
  --file "/absolute/path/to/invoice.pdf" \
  > attachment.json
```

通过标准：
- 输出 `ok: true`。
- 输出 `accessorybillid`。
- `upload.status_code` 是 `200`。

保存单据时把 `attachment.json` 里的 `accessorybillid` 传给 `--accessorybillid`。无附件时传空字符串。

### 6. 保存通用报销单

先做 dry run，检查解析结果和 payload 是否能构造：

```bash
python3 "$SKILL_DIR/scripts/save_general_reimbursement_from_dispatch.py" \
  --base-url "$BASE_URL" \
  --cookie '...' \
  --dispatch-json dispatch.json \
  --zy '摘要及用途' \
  --amount '116.46' \
  --tax-amount '6.99' \
  --vat-amount '123.45' \
  --expense-item '宣传费' \
  --invoice-type '增值税普通发票' \
  --invoice-no '12345678901234567890' \
  --accessorybillid '' \
  --dry-run
```

dry run 通过后去掉 `--dry-run` 正式保存：

```bash
python3 "$SKILL_DIR/scripts/save_general_reimbursement_from_dispatch.py" \
  --base-url "$BASE_URL" \
  --cookie '...' \
  --dispatch-json dispatch.json \
  --zy '摘要及用途' \
  --amount '116.46' \
  --tax-amount '6.99' \
  --vat-amount '123.45' \
  --expense-item '宣传费' \
  --invoice-type '增值税普通发票' \
  --invoice-no '12345678901234567890' \
  --accessorybillid ''
```

通过标准：
- 输出 `ok: true`。
- `response` 中包含保存成功信息、`primarykey`、单据号或等价主键字段。

如需留存调试 payload，可加 `--save-form-out save_form.json`，再用 `post_save_form.py` 复投。

### 7. 浏览器最终核验

保存成功后，用浏览器打开或刷新对应单据页面，确认：
- 单据处于查看模式或保存后状态。
- 摘要、发票号码、金额、税额、收支项目、发票类型正确。
- 附件列表包含已上传文件。

## 异常处理

Cookie 失效：
- 症状：脚本返回登录页、空白 HTML、401/403、`success=false`。
- 处理：在同一 CDP 会话上重新登录成功后，再次执行 **`agent-browser --cdp 9222 cookies get`** → `build_cookie_header.py` → `probe_cookie_context.py`。仅当 CDP 导出不可用时，再退回 `merge_set_cookie_header.py` 或人工复制已认证请求的完整 `Cookie`。

获取 URL 失败：
- 症状：`menu/url returned success=false`。
- 处理：确认账号有通用报销单权限；浏览器打开菜单验证，不要改接口参数。

dispatch 缺字段：
- 症状：保存脚本报 `missing system field ...`。
- 处理：重新打开新增页，捕获当前会话最新 dispatch。仍缺失时，只覆盖用户明确确认的字段。

收支项目或发票类型不支持：
- 症状：脚本报 `unsupported expense item` 或 `unsupported invoice type`。
- 处理：先运行 `--help` 查看可选值；如果业务必须使用未列出的项目，改用浏览器枚举选择或补充映射后再运行，不要猜 PK。

保存失败：
- 先用 `--dry-run --save-form-out save_form.json` 生成 payload。
- 检查 `amount` 是不含税金额，`tax-amount` 是税额，`vat-amount` 是价税合计/报销总额。
- 确认 `accessorybillid` 是本次上传返回值。
- 如果响应提示附件缺失，执行附件上传后重新保存。

## 浏览器兜底

脚本无法完成时才走纯浏览器填写：
- 报销总额必须填发票价税合计。
- 增值税进项税额必须填税额。
- 支付金额不手填，由系统计算。
- 收支项目和发票类型优先用枚举选择。
- 每条费用明细选择完成后必须点击行尾“确认”。
- 发票类型显示可能回显为默认值，但保存结果以接口和最终单据为准。
