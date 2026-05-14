# Multi-Invoice Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-invoice scalar CLI args with a JSON-array input that supports N invoices per reimbursement bill.

**Architecture:** `save_general_reimbursement_from_dispatch.py` loads a JSON file of invoice entries via `--invoices-json`, builds one body row per invoice, and aggregates head-level totals. The pipeline shell script passes the new arg through unchanged. SKILL.md is updated to document the new flow.

**Tech Stack:** Python 3, httpx, argparse, Bash

---

### Task 1: Refactor `save_general_reimbursement_from_dispatch.py` — argparse and data loading

**Files:**
- Modify: `skills/productivity/reimbursement-process-unified/scripts/save_general_reimbursement_from_dispatch.py`

- [ ] **Step 1: Replace old invoice args with `--invoices-json` in argparse**

In `main()` (line 472–513), remove these args and replace with `--invoices-json`:

Remove lines 494–506 (these args):
```python
parser.add_argument("--zy", required=True)
parser.add_argument("--amount", required=True, help="Invoice amount excluding tax")
parser.add_argument("--tax-amount", required=True, help="Invoice tax amount")
parser.add_argument("--vat-amount", required=True, help="Invoice total amount including tax")
parser.add_argument("--deptid", default="")
parser.add_argument("--deptid-v", default="")
parser.add_argument("--jkbxr", default="")
parser.add_argument("--skyhzh", default="")
parser.add_argument("--jsfs", default="")
parser.add_argument("--expense-item", required=True, choices=list(EXPENSE_ITEM_TO_PK), help="Expense item display name")
parser.add_argument("--szxmid", default="", help="Debug override for expense item pk")
parser.add_argument("--invoice-type", required=True, choices=list(INVOICE_TYPE_TO_PK), help="Invoice type display name")
parser.add_argument("--invoice-type-pk", default="", help="Debug override for defitem35")
parser.add_argument("--invoice-no", required=True, help="defitem44")
```

Replace with:
```python
parser.add_argument("--zy", required=True)
parser.add_argument("--invoices-json", required=True, help="Path to JSON file containing invoice array")
parser.add_argument("--deptid", default="")
parser.add_argument("--deptid-v", default="")
parser.add_argument("--jkbxr", default="")
parser.add_argument("--skyhzh", default="")
parser.add_argument("--jsfs", default="")
```

Also remove `--fjzs` (line 488):
```python
parser.add_argument("--fjzs", default="")
```

And remove `--szxmid`, `--invoice-type-pk` from the remaining args.

- [ ] **Step 2: Add invoice loading and validation function**

Add after the `resolve_expense_item_pk` function (after line 277):

```python
INVOICE_REQUIRED_FIELDS = ("amount", "tax_amount", "vat_amount", "invoice_no", "expense_item", "invoice_type")


def load_invoices(path: str) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8")
    invoices = json.loads(text)
    if not isinstance(invoices, list) or len(invoices) == 0:
        raise SystemExit(f"--invoices-json must contain a non-empty array, got: {type(invoices).__name__}")
    for i, inv in enumerate(invoices):
        missing = [f for f in INVOICE_REQUIRED_FIELDS if f not in inv or not str(inv[f]).strip()]
        if missing:
            raise SystemExit(f"invoices[{i}] missing required fields: {', '.join(missing)}")
    return invoices
```

- [ ] **Step 3: Verify the file still parses without syntax errors**

Run: `cd skills/productivity/reimbursement-process-unified/scripts && python3 -c "import save_general_reimbursement_from_dispatch"`
Expected: `ImportError` or `ModuleNotFoundError` for `erm_common` is fine (it's imported at module level), but no `SyntaxError`.

- [ ] **Step 4: Commit**

```bash
git add skills/productivity/reimbursement-process-unified/scripts/save_general_reimbursement_from_dispatch.py
git commit -m "refactor(skills): replace single-invoice args with --invoices-json in argparse"
```

---

### Task 2: Refactor `build_save_form` to build multiple body rows

**Files:**
- Modify: `skills/productivity/reimbursement-process-unified/scripts/save_general_reimbursement_from_dispatch.py`

- [ ] **Step 1: Add `build_body_row` helper function**

Add after the `require_value` function (after line 283). This extracts the per-invoice body row construction from `build_save_form`:

```python
def build_body_row(
    *,
    invoice: dict[str, str],
    shared: dict[str, Any],
) -> dict[str, Any]:
    szxmid = resolve_expense_item_pk(invoice["expense_item"])
    invoice_type_pk = resolve_invoice_type_pk(invoice["invoice_type"])
    amount = invoice["amount"]
    tax_amount = invoice["tax_amount"]
    vat_amount = invoice["vat_amount"]
    return {
        "cls": "nc.vo.ep.bx.BXBusItemVO",
        "paytarget": 0,
        "receiver": shared["jkbxr"],
        "skyhzh": shared["skyhzh"],
        "szxmid": szxmid,
        "vat_amount": money(vat_amount, 2),
        "dwbm": shared["pk_org"],
        "deptid": shared["deptid"],
        "jkbxr": shared["jkbxr"],
        "hkbbje": ZERO8,
        "hkybje": ZERO8,
        "cjkybje": ZERO8,
        "groupbbje": ZERO8,
        "groupzfbbje": ZERO8,
        "grouphkbbje": ZERO8,
        "cjkbbje": ZERO8,
        "groupcjkbbje": ZERO8,
        "globalhkbbje": ZERO8,
        "globalzfbbje": ZERO8,
        "globalcjkbbje": ZERO8,
        "tablecode": "arap_bxbusitem",
        "globalbbje": ZERO8,
        "bzbm": shared["bzbm"],
        "bbhl": shared["bbhl"],
        "defitem35": invoice_type_pk,
        "defitem44": invoice["invoice_no"],
        "defitem13": shared["defitem13"],
        "tax_amount": money(tax_amount, 2),
        "tni_amount": money(amount, 2),
        "orgtax_amount": money(tax_amount, 2),
        "orgvat_amount": money(vat_amount, 2),
        "orgtni_amount": money(amount, 2),
        "grouptax_amount": ZERO8,
        "groupvat_amount": ZERO8,
        "grouptni_amount": ZERO8,
        "globaltax_amount": ZERO8,
        "globalvat_amount": ZERO8,
        "globaltni_amount": ZERO8,
        "groupbbhl": ZERO8,
        "globalbbhl": ZERO8,
        "bbje": money(amount, 2),
        "ybje": money(amount, 2),
        "zfybje": money(amount, 8),
        "zfbbje": money(amount, 8),
        "amount": money(amount, 2),
    }
```

- [ ] **Step 2: Rewrite `build_save_form` signature and body**

Replace the current `build_save_form` function (lines 286–469). The new version takes `invoices` list and aggregates head totals:

```python
def build_save_form(
    args: argparse.Namespace,
    defaults: dict[str, Any],
    invoices: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    head_defaults = defaults.get("head", {})
    body_defaults = defaults.get("body", {})
    cookie = parse_cookie_header(args.cookie)

    pk_org = args.pk_org or head_defaults.get("pk_org") or cookie.get("user_org", "")
    pk_group = args.pk_group or head_defaults.get("pk_group") or cookie.get("pk_unit", "") or cookie.get("pk_group", "")
    pk_org = require_value("head.pk_org", pk_org)
    pk_group = require_value("head.pk_group", pk_group)
    pk_org_v = require_value("head.pk_org_v", args.pk_org_v or head_defaults.get("pk_org_v"))
    pk_fiorg = args.pk_fiorg or head_defaults.get("pk_fiorg") or pk_org
    pk_tradetypeid = require_value("head.pk_tradetypeid", args.pk_tradetypeid or head_defaults.get("pk_tradetypeid"))
    deptid = require_value("head.deptid", args.deptid or head_defaults.get("deptid"))
    deptid_v = require_value("head.deptid_v", args.deptid_v or head_defaults.get("deptid_v") or head_defaults.get("fydeptid_v"))
    jkbxr = require_value("head.jkbxr", args.jkbxr or head_defaults.get("jkbxr") or body_defaults.get("jkbxr"))
    skyhzh = require_value("head.skyhzh", args.skyhzh or head_defaults.get("skyhzh") or body_defaults.get("skyhzh"))
    jsfs = require_value("head.jsfs", args.jsfs or head_defaults.get("jsfs"))
    bzbm = require_value("head.bzbm", args.bzbm or head_defaults.get("bzbm") or body_defaults.get("bzbm"))
    bbhl = str(head_defaults.get("bbhl") or body_defaults.get("bbhl") or "1.00000000")
    operator = args.operator or head_defaults.get("operator") or cookie.get("userid", "")
    creator = args.creator or head_defaults.get("creator") or cookie.get("userid", "")
    jkbxr_mobile = args.jkbxr_mobile or head_defaults.get("jkbxr_mobile") or ""
    zyx18 = require_value("head.zyx18", args.zyx18 or head_defaults.get("zyx18"))
    zyx20 = require_value("head.zyx20", args.zyx20 or head_defaults.get("zyx20"))
    defitem13 = require_value("body.defitem13", args.defitem13 or body_defaults.get("defitem13"))
    pk_payorg = head_defaults.get("pk_payorg") or pk_org
    pk_payorg_v = head_defaults.get("pk_payorg_v") or pk_org_v
    fydwbm = head_defaults.get("fydwbm") or pk_org
    fydwbm_v = head_defaults.get("fydwbm_v") or pk_org_v
    bill_date = args.bill_date or datetime.now().strftime("%Y-%m-%d")
    djrq = f"{bill_date} 00:00:00"
    creationtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    shared = {
        "pk_org": pk_org,
        "deptid": deptid,
        "jkbxr": jkbxr,
        "skyhzh": skyhzh,
        "bzbm": bzbm,
        "bbhl": bbhl,
        "defitem13": defitem13,
    }

    body_rows = [build_body_row(invoice=inv, shared=shared) for inv in invoices]

    total_amount = money(str(sum(Decimal(inv["amount"]) for inv in invoices)), 2)
    total_tax = money(str(sum(Decimal(inv["tax_amount"]) for inv in invoices)), 2)
    total_vat = money(str(sum(Decimal(inv["vat_amount"]) for inv in invoices)), 2)

    bill_head = {
        "djrq": djrq,
        "zy": args.zy,
        "zfbbje": total_amount,
        "cjkbbje": ZERO8,
        "deptid": deptid,
        "fydeptid_v": deptid_v,
        "jkbxr": jkbxr,
        "skyhzh": skyhzh,
        "fjzs": len(invoices),
        "jsfs": jsfs,
        "deptid_v": deptid_v,
        "bzbm": bzbm,
        "bbhl": bbhl,
        "vat_amount": total_vat,
        "total": total_amount,
        "dwbm": pk_org,
        "fydeptid": deptid,
        "jkbxr_mobile": jkbxr_mobile,
        "pk_org_v": pk_org_v,
        "selected": "N",
        "pk_org": pk_org,
        "pk_tradetypeid": pk_tradetypeid,
        "pk_group": pk_group,
        "pk_fiorg": pk_fiorg,
        "djlxbm": TRADE_TYPE,
        "bbje": total_amount,
        "ybje": total_amount,
        "zfybje": total_amount,
        "hkybje": ZERO8,
        "hkbbje": ZERO8,
        "djzt": 1,
        "spzt": -1,
        "groupbbhl": ZERO8,
        "groupbbje": ZERO8,
        "sxbz": 0,
        "groupcjkbbje": ZERO8,
        "iscostshare": "N",
        "grouphkbbje": ZERO8,
        "isexpamt": "N",
        "groupzfbbje": ZERO8,
        "globalbbhl": ZERO8,
        "globalbbje": ZERO8,
        "globalcjkbbje": ZERO8,
        "globalhkbbje": ZERO8,
        "globalzfbbje": ZERO8,
        "cjkybje": ZERO8,
        "djdl": "bx",
        "qcbz": "N",
        "operator": operator,
        "dwbm_v": pk_org_v,
        "isneedimag": "N",
        "isexpedited": "N",
        "pk_payorg_v": pk_payorg_v,
        "pk_payorg": pk_payorg,
        "fydwbm": fydwbm,
        "fydwbm_v": fydwbm_v,
        "zyx16": head_defaults.get("zyx16") or "false",
        "zyx18": zyx18,
        "zyx20": zyx20,
        "paytarget": 0,
        "receiver": jkbxr,
        "tax_amount": total_tax,
        "tni_amount": total_amount,
        "orgtax_amount": total_tax,
        "orgvat_amount": total_vat,
        "orgtni_amount": total_amount,
        "grouptax_amount": ZERO8,
        "groupvat_amount": ZERO8,
        "grouptni_amount": ZERO8,
        "globaltax_amount": ZERO8,
        "globalvat_amount": ZERO8,
        "globaltni_amount": ZERO8,
        "creator": creator,
        "creationtime": creationtime,
    }
    save_form = {
        "tradetype": TRADE_TYPE,
        "pk_billtemplet": args.pk_billtemplet,
        "bill": json.dumps(
            {"head": bill_head, "body": {"bodys": body_rows}},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "state": "add",
        "accessorybillid": args.accessorybillid,
        "card_html": "jkbxcard",
    }
    resolved = {
        "pk_org": pk_org,
        "pk_group": pk_group,
        "pk_org_v": pk_org_v,
        "pk_fiorg": pk_fiorg,
        "source": "dispatch json",
        "defitem13": defitem13,
        "invoice_count": len(invoices),
        "expenses": [
            {"name": inv["expense_item"], "pk": resolve_expense_item_pk(inv["expense_item"])}
            for inv in invoices
        ],
        "invoice_types": [
            {"name": inv["invoice_type"], "pk": resolve_invoice_type_pk(inv["invoice_type"])}
            for inv in invoices
        ],
    }
    return save_form, resolved
```

- [ ] **Step 3: Update `main()` to use `load_invoices` and pass invoices to `build_save_form`**

In `main()`, replace the direct call to `build_save_form` (around lines 515–517) with:

```python
invoices = load_invoices(args.invoices_json)
save_form, resolved = build_save_form(args, defaults, invoices)
```

- [ ] **Step 4: Verify no syntax errors**

Run: `cd skills/productivity/reimbursement-process-unified/scripts && python3 -c "import save_general_reimbursement_from_dispatch"`
Expected: No SyntaxError.

- [ ] **Step 5: Commit**

```bash
git add skills/productivity/reimbursement-process-unified/scripts/save_general_reimbursement_from_dispatch.py
git commit -m "feat(skills): build multiple body rows from --invoices-json with head aggregation"
```

---

### Task 3: Update `run_reimbursement_pipeline.sh`

**Files:**
- Modify: `skills/productivity/reimbursement-process-unified/scripts/run_reimbursement_pipeline.sh`

- [ ] **Step 1: Update header comment to reflect new required args**

In the header comment (lines 20–21), replace:

```bash
# Required args:
#   --zy --amount --tax-amount --vat-amount --expense-item --invoice-type --invoice-no
```

with:

```bash
# Required args:
#   --zy --invoices-json <path>
```

- [ ] **Step 2: No other changes needed**

The pipeline passes `"$@"` directly to the save script (line 302 and 314), so `--invoices-json` flows through automatically. No functional code change required in the shell script.

- [ ] **Step 3: Commit**

```bash
git add skills/productivity/reimbursement-process-unified/scripts/run_reimbursement_pipeline.sh
git commit -m "docs(skills): update pipeline header to reflect --invoices-json arg"
```

---

### Task 4: Dry-run test with HAR data

**Files:**
- Test data: `skills/productivity/reimbursement-process-unified/har/10.83.2.11.通用报销单多.har`

- [ ] **Step 1: Create a test invoices.json from HAR data**

Create a temp file and verify the save script can build a correct payload:

```bash
cat > /tmp/test_invoices.json << 'EOF'
[
  {"amount": "60", "tax_amount": "6", "vat_amount": "66", "invoice_no": "147258369", "expense_item": "党建工作经费", "invoice_type": "增值税普通发票"},
  {"amount": "90", "tax_amount": "9", "vat_amount": "99", "invoice_no": "258369147", "expense_item": "办公费-办公用品", "invoice_type": "增值税普通发票"}
]
EOF
```

- [ ] **Step 2: Extract dispatch defaults from the HAR for a dry-run test**

Extract the dispatch response from the HAR entry (entry 65, the first dispatch POST that contains `dataTables`), save to `/tmp/test_dispatch.json`.

Then run:

```bash
cd skills/productivity/reimbursement-process-unified/scripts
python3 save_general_reimbursement_from_dispatch.py \
  --cookie "user_org=0001Q1100000000014QK; pk_unit=0001Q1100000000006YP; datasource=hnzb65; userid=1001Q110000000000JB0; usercode=82031001" \
  --dispatch-json /tmp/test_dispatch.json \
  --invoices-json /tmp/test_invoices.json \
  --zy "0514测试" \
  --dry-run --save-form-out /tmp/test_save_form.json
```

- [ ] **Step 3: Validate the output matches HAR structure**

Verify `/tmp/test_save_form.json`:

```python
import json
data = json.loads(open("/tmp/test_save_form.json").read())
form = data["save_form"]
bill = json.loads(form["bill"])

# Head totals = sum of both invoices
assert bill["head"]["total"] == "150.00"
assert bill["head"]["tax_amount"] == "15.00"
assert bill["head"]["vat_amount"] == "165.00"
assert bill["head"]["fjzs"] == 2

# Two body rows
assert len(bill["body"]["bodys"]) == 2
assert bill["body"]["bodys"][0]["defitem44"] == "147258369"
assert bill["body"]["bodys"][1]["defitem44"] == "258369147"
assert bill["body"]["bodys"][0]["amount"] == "60.00"
assert bill["body"]["bodys"][1]["amount"] == "90.00"

# Per-invoice expense items differ
assert bill["body"]["bodys"][0]["szxmid"] != bill["body"]["bodys"][1]["szxmid"]
```

- [ ] **Step 4: Commit test artifacts (if any temp scripts were created for extraction)**

Skip if no new files.

---

### Task 5: Update SKILL.md

**Files:**
- Modify: `skills/productivity/reimbursement-process-unified/SKILL.md`

- [ ] **Step 1: Replace "准备信息" section (lines 70–81)**

Replace the current single-invoice bullet list with multi-invoice JSON description. Change lines 72–81 from:

```markdown
执行前先确认这些输入：
- ERM 登录账号和密码（仅用于设置 `ERM_USERID` / `ERM_PASSWORD` 后调用 `login_erm.sh`）。
- 发票号码：`--invoice-no`。
- 不含税金额：`--amount`。
- 税额：`--tax-amount`。
- 价税合计：`--vat-amount`。
- 摘要/用途：`--zy`。
- 收支项目显示名：由 AI 根据 `--zy` 推断（见「收支项目推断」），推断后请用户确认。
- 发票类型：`--invoice-type`（如 `增值税普通发票`）。
- 附件：若需上传，路径须在 `ACCOUNT_WORKSPACE` 下（见 §1）。
```

to:

```markdown
执行前先确认这些输入：
- ERM 登录账号和密码（仅用于设置 `ERM_USERID` / `ERM_PASSWORD` 后调用 `login_erm.sh`）。
- 摘要/用途：`--zy`（整张报销单共用）。
- 发票信息：通过 `--invoices-json` 传入 JSON 文件，每张发票包含：
  - `amount`：不含税金额。
  - `tax_amount`：税额。
  - `vat_amount`：价税合计。
  - `invoice_no`：发票号码。
  - `expense_item`：收支项目显示名（AI 根据 `--zy` 推断，见「收支项目推断」，推断后请用户确认）。
  - `invoice_type`：发票类型（如 `增值税普通发票`）。
- 附件：若需上传，路径须在 `ACCOUNT_WORKSPACE` 下（见 §1）。
```

- [ ] **Step 2: Update "收支项目推断" section (lines 122–127)**

Change from single `--zy` → single `--expense-item` to per-invoice inference:

```markdown
## 收支项目推断

AI 在构造 `invoices.json` 前，根据每张发票的 `--zy` 和发票内容自动推断对应的 `expense_item`：

1. 读取 `scripts/save_general_reimbursement_from_dispatch.py` 中的 `EXPENSE_ITEM_TO_PK`。
2. 对每张发票语义匹配后向用户确认；不确定时给出 2–3 个候选项。
3. 将确认后的 `expense_item` 写入 `invoices.json` 对应条目。

注意：每张发票的 `expense_item` 可以不同。`resolve_expense_item_pk` 为最终防线；值须与字典 key 完全一致。
```

- [ ] **Step 3: Update pipeline invocation example (lines 162–177)**

Replace the current example with:

```bash
export SKILL_DIR="<absolute-path-to-this-skill>"
export ERM_ACCOUNT='<account>'
export ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT}}"
export PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
export DRY_RUN=0

# AI generates invoices.json before calling the pipeline
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

- [ ] **Step 4: Update "环境变量" table — remove old single-invoice references**

In the table (lines 185–197), no changes needed since the table documents env vars, not CLI args.

- [ ] **Step 5: Commit**

```bash
git add skills/productivity/reimbursement-process-unified/SKILL.md
git commit -m "docs(skills): update SKILL.md for multi-invoice --invoices-json flow"
```

---

## Self-Review

**Spec coverage:**
- Data model (JSON array with 6 fields) → Task 1 (validation), Task 2 (body rows)
- Head aggregation → Task 2 (sum in build_save_form)
- CLI changes (remove old args, add --invoices-json) → Task 1
- Pipeline shell update → Task 3
- SKILL.md updates → Task 5
- Testing with HAR data → Task 4

**Placeholder scan:** No TBD/TODO found. All steps contain actual code.

**Type consistency:** `load_invoices` returns `list[dict[str, str]]`, passed to `build_save_form` which iterates and accesses string keys. `build_body_row` takes `invoice: dict[str, str]` and `shared: dict[str, Any]`. All consistent.
