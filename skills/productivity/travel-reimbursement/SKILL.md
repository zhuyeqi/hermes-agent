---
name: travel-reimbursement
description: 自动处理内网 ERM 差旅费报销单。适用于根据差旅费用信息创建差旅费报销单、上传附件、保存单据；agent-browser 以 --profile 模式管理浏览器，负责登录、Cookie 导出、HAR 捕获 dispatch 初始化数据和最终核验。所有持久化数据按账号隔离到专属 ACCOUNT_WORKSPACE 目录，避免多用户串 cookie/token/明细/附件。
author: Hermes Agent
version: 0.2.0
created: 2026-05-13
updated: 2026-05-13
tags: [finance, reimbursement, travel, internal-system, browser, scripts]
status: alpha
requires:
  - browser
  - python3
  - python-httpx
---

# 差旅费报销单处理流程

> **状态：alpha 第一版可验证。** 已实现差旅费单据类型、默认值提取（含三张明细表）、JSON 明细输入、动态补贴标准、多发票/多行明细保存、账号工作空间隔离。

## 目标

用“浏览器 + 脚本”的混合方式创建 ERM 差旅费报销单。

成功标准：
- 成功登录 ERM，并拿到有效 Cookie。
- 拿到差旅费报销单新增页面 URL（tradetype=264X-Cxx-CLBX）。
- 从新增页的 `/iwebap/evt/dispatch` 响应提取到系统默认字段（head、transport、hotel、subsidy 四组）。
- 如需附件，上传成功并拿到 `accessorybillid`。
- 保存接口返回成功，响应里包含单据主键或可在浏览器中看到保存后的单据。
- 所有中间产物（cookies、dispatch、defaults、附件、save_form、save_result）都在账号专属 `ACCOUNT_WORKSPACE` 目录下，不同账号严格隔离。

## 分工原则

优先用脚本做确定性操作：
- 获取差旅费报销单 URL。
- 解析 Cookie 上下文。
- 从 dispatch 响应提取默认字段（支持 head、transport、hotel、subsidy）。
- 上传附件（复用通用报销单链路，billtype=264X-Cxx-CLBX）。
- 构造并提交保存表单（支持多 transports/hotels/subsidies 明细）。

只在这些场景使用浏览器（agent-browser `--profile` 模式）：
- 登录 ERM（AI 交互式操作，不写入脚本）。
- Cookie 导出：`agent-browser --profile $PROFILE_DIR cookies get`。
- HAR 录制：捕获 `/iwebap/evt/dispatch` 响应用于提取默认字段。
- 保存后核验单据状态，或脚本不支持的异常 UI 流程。

不要依赖旧的页面元素 ref。每次浏览器操作前重新观察页面。

## 前置条件

- **系统 URL（ERM 基础地址）**：写死在 `scripts/erm_common.py` 的 `ERM_BASE_URL`（当前为 `http://10.83.2.11:8008`）。
- 登录页面：`http://10.83.2.11:8008/portal/app/mockapp/login.jsp?lrid=1`。
- ERM 登录账号和密码：必须由用户提供。

## 准备信息

执行前先确认这些输入：
- ERM 登录账号和密码：必须由用户提供。
- **差旅明细 JSON 文件**：必须包含至少一条 transports/hotels/subsidies，放在账号工作空间下。
- **附件文件（可选）**：发票/凭证等文件，放在账号工作空间下。

不要把账号密码、Cookie、token 写入最终回复、提交记录或持久化文档。

## AI 文件解析行为规范

当用户提供发票文件（图片/PDF/OFD 等）用于解析时，AI 必须遵循以下流程：

1. 先解析文件获取发票信息（发票号、金额、税额等）
2. 解析完成后，**必须自动设置 `ATTACHMENT_FILE` 或 `ATTACHMENT_FILES` 环境变量**，指向用户提供的原始文件路径（必须在 ACCOUNT_WORKSPACE 内）
3. 不要询问用户“是否需要上传附件”
4. 然后继续执行报销流程

```bash
# AI 解析完文件后，必须设置此环境变量（确保路径在 ACCOUNT_WORKSPACE 下）
export ATTACHMENT_FILE="${ACCOUNT_WORKSPACE}/attachments/2026-05-13-beijing/train.pdf"

# 然后执行 pipeline
"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh"
```

## 账号工作空间隔离

所有持久化数据都必须按账号隔离，避免多用户串 cookie/token/明细/附件。

- `ERM_ACCOUNT`：必填账号标识（例如用户名）。
- `ACCOUNT_WORKSPACE`：账号专属工作空间根目录，默认 `/opt/data/erm-workspace/${ERM_ACCOUNT}`。
- `PROFILE_DIR`：浏览器 profile 目录，默认 `${ACCOUNT_WORKSPACE}/browser-profile`。
- `RUN_DIR`：当前运行产物目录，默认 `${ACCOUNT_WORKSPACE}/runs/travel-$(date +%Y%m%d-%H%M%S)`。
- `ITEMS_JSON`：差旅明细 JSON 路径，**必须在 ACCOUNT_WORKSPACE 之内**，pipeline 会校验前缀。
- `ATTACHMENT_FILE` / `ATTACHMENT_FILES`：附件路径，**必须在 ACCOUNT_WORKSPACE 之内**，pipeline 会校验前缀。

推荐目录布局：
```
/opt/data/erm-workspace/${ERM_ACCOUNT}/
  browser-profile/      # agent-browser profile（持久化 session）
  items/                # 差旅明细 JSON 文件
  attachments/          # 发票/凭证附件文件
    2026-05-13-beijing/
      train.pdf
      hotel.pdf
  runs/                 # 每次运行的中间产物（自动生成时间戳目录）
    travel-20260513-153000/
```

## 差旅明细 JSON 契约

差旅明细采用 JSON 文件输入（`--items-json`），格式如下：

```json
{
  "summary": "北京出差",
  "bill_date": "2026-05-13",
  "training_fee": "否",
  "transports": [
    {
      "departure_date": "2026-05-04",
      "arrival_date": "2026-05-07",
      "vehicle": "火车（二等座）",
      "invoice_form": "火车电子报销凭证",
      "invoice_no": "T123",
      "amount": "500.00",
      "tax_amount": "0.00"
    }
  ],
  "hotels": [
    {
      "city_type": "其他人员/省会直辖市",
      "purpose": "住宿",
      "days": 2,
      "invoice_type": "增值税普通发票",
      "invoice_no": "H789",
      "amount": "600.00",
      "tax_amount": "0.00"
    }
  ],
  "subsidies": [
    {
      "days": 2,
      "tool": "火车",
      "official_car_pickup": "否",
      "hosted_by_counterparty": "否"
    }
  ]
}
```

### 字段说明

**顶层字段**：
- `summary`（必填）：报销摘要，写入 head `zy`。
- `bill_date`（可选）：单据日期（YYYY-MM-DD），写入 head `djrq`，缺省用当天。
- `training_fee`（可选）：是否包含培训费，默认“否”，映射到 head `zyx11`。
- `transports`：交通费用明细数组。
- `hotels`：住宿费用明细数组。
- `subsidies`：出差补贴明细数组。

**必须至少包含一条 transports/hotels/subsidies**。

### transports 字段

- `departure_date`（必填）：出发日期（YYYY-MM-DD），写入 `defitem1`。
- `arrival_date`（必填）：到达日期（YYYY-MM-DD），写入 `defitem2`。
- `vehicle`（必填）：交通工具名称，映射到 `defitem5`，支持：飞机（商务舱）、飞机（经济舱）、火车（商务座）、火车（一等座）、火车（二等座）、出租车、公交/地铁、长途巴士、轮船、其他。
- `invoice_form`（必填）：发票形式名称，映射到 `defitem15`，支持：飞机行程单、火车电子报销凭证、火车纸质报销凭证、长途巴士、轮船、出租车报销凭证。
- `invoice_no`（必填）：发票号，写入 `defitem44`。
- `amount`（必填）：票面总价（含税），写入 `vat_amount` / `amount` / `bbje` 等。
- `tax_amount`（可选）：税额，缺省 0.00。
- `receiver`（可选）：收款人，缺省用报销人。
- `bank_account`（可选）：收款账户，缺省用 dispatch 默认收款账户。

### hotels 字段

- `city_type`（必填）：住宿城市报销类型名称，映射到 `defitem16`，支持：公司负责人/一般地区、公司负责人/省会直辖市、公司负责人/北京上海广深、其他人员/一般地区、其他人员/省会直辖市、其他人员/北京上海广深。
- `purpose`（可选）：用途，写入 `defitem10`。
- `days`（必填）：住宿天数，写入 `defitem20`。
- `invoice_type`（必填）：发票类型名称，映射到 `defitem35`，支持：增值税专用发票、增值税普通发票。
- `invoice_no`（必填）：发票号，写入 `defitem44`。
- `amount`（必填）：报销金额，写入 `vat_amount` / `amount`。
- `tax_amount`（可选）：税额，缺省 0.00。
- `receiver`（可选）：收款人，缺省用报销人。
- `bank_account`（可选）：收款账户，缺省用 dispatch 默认收款账户。

### subsidies 字段

- `days`（必填）：出差天数，写入 `defitem9`。
- `tool`（必填）：出差工具名称，映射到 `defitem40`，支持：火车、火车（过夜）、长途巴士、轮船。
- `official_car_pickup`（必填）：是否使用公司公务用车接送站，映射到 `defitem36`，支持：是、否。
- `hosted_by_counterparty`（必填）：对方单位是否接待用餐用车，映射到 `defitem37`，支持：是、否。
- `standard`（可选）：补贴标准（元/天），如果提供则使用此值；否则从 dispatch defaults 的 `subsidy.defitem11` 动态读取；如果两者都缺失则报错。
- `amount`（可选）：补贴总金额（标准×天数），如果提供则使用此值；否则按标准×天数计算。

**重要**：补贴金额 = `标准 × 天数`。标准来源优先级：`subsidies[].amount` > `subsidies[].standard` > `defaults.subsidy.defitem11`。dry-run 输出会标记 `standard_source` 为 `items` 或 `dispatch`。

## 脚本位置

本技能自带脚本在 `scripts/`：
- `erm_common.py`：ERM 基础地址、HTTP 工具函数。
- `build_cookie_header.py`：从 cookies JSON 生成并校验 `Cookie` 请求头。
- `merge_set_cookie_header.py`：兜底 Cookie 生成。
- `probe_cookie_context.py`：检查 Cookie 是否包含 ERM 会话关键字段。
- `get_travel_reimbursement_url.py`：调用菜单接口获取差旅费报销单新增页 URL（tradetype=264X-Cxx-CLBX）。
- `extract_dispatch_defaults.py`：从 dispatch 响应提取保存表单必需默认值，支持 head、transport、hotel、subsidy 四组。
- `upload_reimbursement_attachment.py`：上传附件并返回 `accessorybillid`（billtype=264X-Cxx-CLBX）。
- `save_travel_reimbursement_from_dispatch.py`：从 dispatch 默认值和 items JSON 构造并保存单据，支持多明细、动态补贴。
- `run_reimbursement_pipeline.sh`：单入口脚本，自动完成登录检查、Cookie 导出、HAR 录制、默认值提取、附件上传、单据保存。

运行时用当前技能目录，不要写死本机绝对路径：

```bash
SKILL_DIR="<actual-skill-directory>"
```

## 推荐流程（两步）

### 1) 登录（AI 交互式，使用 --profile 模式）

AI 询问用户 ERM 账号和密码，然后操作浏览器完成登录：

```bash
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="/opt/data/erm-workspace/${ERM_ACCOUNT}"
mkdir -p "$ACCOUNT_WORKSPACE"/{browser-profile,items,attachments,runs}
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"

agent-browser --profile "$PROFILE_DIR" open "http://10.83.2.11:8008/portal/app/mockapp/login.jsp?lrid=1"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# AI 根据页面结构，填入用户提供的账号密码
agent-browser --profile "$PROFILE_DIR" fill @e<账号ref> '<account>'
agent-browser --profile "$PROFILE_DIR" fill @e<密码ref> '<password>'
agent-browser --profile "$PROFILE_DIR" click @e<登录ref>
agent-browser --profile "$PROFILE_DIR" wait --load networkidle
```

### 2) 执行单入口脚本

```bash
export SKILL_DIR="<actual-skill-directory>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="/opt/data/erm-workspace/${ERM_ACCOUNT}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"

# 确保 ITEMS_JSON 和附件在 ACCOUNT_WORKSPACE 下
export ITEMS_JSON="${ACCOUNT_WORKSPACE}/items/2026-05-13-beijing.json"
export ATTACHMENT_FILES="${ACCOUNT_WORKSPACE}/attachments/2026-05-13-beijing/train.pdf:${ACCOUNT_WORKSPACE}/attachments/2026-05-13-beijing/hotel.pdf"

# 可选：dry-run 只验证 payload
export DRY_RUN=1

"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh"
```

产物文件（在 `$RUN_DIR`，自动生成）：
- `cdp_cookies.json`
- `menu_url.json`
- `dispatch.json`
- `defaults.json`
- `attachment_*.json`
- `save_form.json`
- `save_result.json`

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `SKILL_DIR` | 是 | — | 技能目录路径 |
| `ERM_ACCOUNT` | 是 | — | 账号标识，用于工作空间隔离 |
| `ACCOUNT_WORKSPACE` | 否 | `/opt/data/erm-workspace/${ERM_ACCOUNT}` | 账号专属工作空间根目录 |
| `ITEMS_JSON` | 是 | — | 差旅明细 JSON 路径（必须在 ACCOUNT_WORKSPACE 内） |
| `PROFILE_DIR` | 否 | `${ACCOUNT_WORKSPACE}/browser-profile` | agent-browser profile 目录 |
| `COOKIE` | 否 | 自动从 profile 导出 | 手动指定的 Cookie 头 |
| `ATTACHMENT_FILE` | 否 | — | 单附件本地路径（必须在 ACCOUNT_WORKSPACE 内） |
| `ATTACHMENT_FILES` | 否 | — | 多附件绝对路径列表，冒号分隔（必须在 ACCOUNT_WORKSPACE 内） |
| `RUN_DIR` | 否 | `${ACCOUNT_WORKSPACE}/runs/travel-$(date +%Y%m%d-%H%M%S)` | 运行产物目录 |
| `DRY_RUN` | 否 | `0` | 设为 `1` 仅构造 payload 不提交 |

## 执行契约（Hard Gates）

- **Gate.A（Login）**：脚本打开登录页后 URL 不含 `login.jsp`。
- **Gate.B（menu_url.json）**：`menu_url.json` 包含 `result.absolute_url`，且 `success=true`。
- **Gate.C（dispatch.json）**：HAR 中找到 `/iwebap/evt/dispatch` 响应，解析后包含 `dataTables`。
- **Gate.D（defaults.json）**：必须包含关键默认字段（head 必填字段，至少一张明细表有字段）。
- **Gate.E（attachment）**：如要求附件，必须 `ok=true` 且有 `accessorybillid`。
- **隔离校验**：`ITEMS_JSON` 和 `ATTACHMENT_FILES` 必须在 `ACCOUNT_WORKSPACE` 之内（绝对路径前缀匹配），否则停机报错。

失败处理规范：
- `dispatch` 只允许一次标准重试。
- 重试仍失败必须停机并输出证据。
- 账号隔离路径不满足必须停机，禁止跨账号串文件。

## 验证与回归清单（必须执行）

成功路径：
- `dispatch.json` 存在且含 `dataTables`。
- `defaults.json` 关键字段齐全（head、transport、hotel、subsidy）。
- `save_form.json` 的 `bill.head.djlxbm == "264X-Cxx-CLBX"`。
- `save_form.json` 的 `bill.body.bodys` 包含对应明细行（`tablecode` 为 `arap_bxbusitem`、`other`、`bzitem`）。
- 补贴金额的 `standard_source` 标记为 `dispatch` 或 `items`，不出现硬编码。
- `save_result.json` 显示 `ok=true`，并包含单据主键或单据号。
- 浏览器最终核验字段和附件一致。
- 所有产物文件都在 `RUN_DIR`（位于 `ACCOUNT_WORKSPACE` 内）。

失败路径：
- `dispatch` 缺失/解析失败：仅重试一次；仍失败停机。
- `defaults` 缺字段：回到新增页重抓；禁止猜测字段。
- 附件失败且业务要求附件：必须停机。
- `ITEMS_JSON` 或附件路径不在 `ACCOUNT_WORKSPACE` 内：必须停机。

## 浏览器兜底边界

- **允许**：登录、最终核验、极少数 UI 异常确认。
- **禁止**：在 `dispatch/defaults` 缺失时继续提交；猜测系统字段；跨账号共享文件或 cookie。
