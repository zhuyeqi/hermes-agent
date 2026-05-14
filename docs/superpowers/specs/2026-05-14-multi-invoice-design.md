# Multi-Invoice Support for General Reimbursement

Date: 2026-05-14

## Goal

Support multiple invoices per reimbursement bill. Currently the pipeline only
accepts a single invoice via scalar CLI args. Replace that with a JSON-array
input that carries N invoices, each with its own amount, tax, invoice number,
expense item, and invoice type.

## Data Model

### Input: `--invoices-json <path>`

A JSON file containing an array of invoice objects. Every field is required.

```json
[
  {
    "amount": "60",
    "tax_amount": "6",
    "vat_amount": "66",
    "invoice_no": "147258369",
    "expense_item": "党建工作经费",
    "invoice_type": "增值税普通发票"
  },
  {
    "amount": "90",
    "tax_amount": "9",
    "vat_amount": "99",
    "invoice_no": "258369147",
    "expense_item": "办公费-办公用品",
    "invoice_type": "增值税普通发票"
  }
]
```

### Head aggregation

Head-level financial fields are the sum of all body rows.

| Head field | Source |
|---|---|
| `zfbbje`, `total`, `bbje`, `ybje`, `zfybje` | sum(body.amount) |
| `tax_amount`, `orgtax_amount` | sum(body.tax_amount) |
| `vat_amount`, `orgvat_amount` | sum(body.vat_amount) |
| `tni_amount`, `orgtni_amount` | sum(body.amount) |
| `fjzs` | len(invoices) |

### Body rows

One `body_row` per invoice entry. Shared fields (`defitem13`, `deptid`,
`jkbxr`, `skyhzh`, `bzbm`, `bbhl`, etc.) come from dispatch defaults and are
identical across all rows. Per-invoice fields vary per row:

- `amount`, `tax_amount`, `vat_amount`, `tni_amount`
- `orgtax_amount`, `orgvat_amount`, `orgtni_amount`
- `bbje`, `ybje`, `zfybje`, `zfbbje`
- `szxmid` (resolved from `expense_item`)
- `defitem35` (resolved from `invoice_type`)
- `defitem44` (invoice number)

## CLI Changes

### `save_general_reimbursement_from_dispatch.py`

**Removed args:**

- `--amount`, `--tax-amount`, `--vat-amount`
- `--invoice-no`
- `--expense-item`, `--szxmid`
- `--invoice-type`, `--invoice-type-pk`
- `--fjzs`

**Added args:**

- `--invoices-json <path>` — required, path to the JSON array file

**Kept args:**

- `--defitem13` — shared across all body rows, resolved from dispatch defaults;
  kept as an optional override arg

### `run_reimbursement_pipeline.sh`

- Remove `--amount --tax-amount --vat-amount --invoice-no --expense-item --invoice-type --invoice-type-pk --fjzs` from required args documentation
- Add `--invoices-json <path>` as required
- `--zy` remains as the shared summary field
- Pipeline passes `"$@"` to save script unchanged

### Invocation example

```bash
"$SKILL_DIR/scripts/run_reimbursement_pipeline.sh" \
  --zy '0514测试' \
  --invoices-json "$RUN_DIR/invoices.json"
```

AI generates `invoices.json` from parsed invoice files or user-described data
before calling the pipeline.

## Script Internal Changes

### `build_save_form` refactor

Before: builds one `body_row` from scalar args, head amounts = body amounts.

After:

1. Load invoices from `--invoices-json`.
2. Validate: non-empty array, each entry has all 6 required fields.
3. For each invoice, resolve `expense_item` → `szxmid` and `invoice_type` →
   `defitem35` using existing lookup tables.
4. Build one `body_row` dict per invoice.
5. Aggregate head amounts from all body rows.
6. Return `save_form` with `{"bodys": [row_0, row_1, ...]}`.

### `defitem13` handling

`defitem13` is shared across all body rows. Resolved once from dispatch
defaults (or `--defitem13` override) and applied to every row.

## SKILL.md Updates

- **准备信息**: replace single-invoice bullet list with multi-invoice JSON
  format description.
- **收支项目推断**: explain that AI infers `expense_item` per invoice, confirms
  each with the user.
- **推荐流程 §2**: show `--invoices-json` invocation.
- **执行契约**: no gate changes; validation adds invoice-array checks.

## Scope

Files to modify:

1. `scripts/save_general_reimbursement_from_dispatch.py` — core refactor
2. `scripts/run_reimbursement_pipeline.sh` — arg passthrough, remove old single-invoice required-args check
3. `SKILL.md` — documentation update

No new files. No pipeline gate changes. No changes to login, cookie, dispatch,
or attachment upload steps.
