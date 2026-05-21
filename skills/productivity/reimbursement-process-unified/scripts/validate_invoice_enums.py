"""Validate invoice expense_item / invoice_type against ERM dictionaries (preflight only)."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

from erm_enums import EXPENSE_ITEM_TO_PK, INVOICE_TYPE_TO_PK

# Hints only — preflight requires exact dictionary keys in invoices.json (no silent rewrite).
INVOICE_TYPE_ALIASES: dict[str, str] = {
    "普票": "增值税普通发票",
    "普通发票": "增值税普通发票",
    "增值税普票": "增值税普通发票",
    "专票": "增值税专用发票",
    "增值税专票": "增值税专用发票",
}


def suggest(value: str, allowed: list[str], n: int = 5) -> list[str]:
    return difflib.get_close_matches(value, allowed, n=n, cutoff=0.45)


def validate_invoices(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expense_keys = sorted(EXPENSE_ITEM_TO_PK.keys())
    invoice_keys = sorted(INVOICE_TYPE_TO_PK.keys())

    for i, inv in enumerate(data):
        raw_expense = str(inv.get("expense_item", "")).strip()
        raw_invoice = str(inv.get("invoice_type", "")).strip()

        if raw_expense not in EXPENSE_ITEM_TO_PK:
            issues.append(
                {
                    "index": i,
                    "field": "expense_item",
                    "value": raw_expense,
                    "error_code": "invoice_enum_invalid",
                    "message": f"收支项目不在系统字典中: {raw_expense!r}",
                    "suggestions": suggest(raw_expense, expense_keys),
                }
            )

        if raw_invoice not in INVOICE_TYPE_TO_PK:
            canonical = INVOICE_TYPE_ALIASES.get(raw_invoice)
            entry: dict[str, Any] = {
                "index": i,
                "field": "invoice_type",
                "value": raw_invoice,
                "error_code": "invoice_enum_invalid",
                "message": f"发票类型不在系统字典中: {raw_invoice!r}",
                "allowed_invoice_types": invoice_keys,
                "suggestions": suggest(raw_invoice, invoice_keys),
            }
            if canonical:
                entry["hint"] = f"请改为字典精确名称: {canonical!r}（勿使用别名 {raw_invoice!r}）"
            issues.append(entry)

    return issues


def main() -> int:
    p = argparse.ArgumentParser(description="Validate invoices.json enums before login/pipeline")
    p.add_argument("--invoices-json", required=True)
    args = p.parse_args()

    path = Path(args.invoices_json)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "invoice_json_invalid",
                    "message": str(e),
                    "hint": "修复 INVOICES_JSON 后重新运行 preflight_check.sh",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4

    if not isinstance(data, list) or not data:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "invoice_json_invalid",
                    "message": "invoices must be a non-empty array",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4

    issues = validate_invoices(data)
    if issues:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "invoice_enum_invalid",
                    "message": f"{len(issues)} invoice field(s) not in ERM dictionary",
                    "hint": "修正 invoices.json：expense_item / invoice_type 须与 scripts/lib/erm_enums.py 的 key 完全一致",
                    "issues": issues,
                    "allowed_expense_items": expense_keys_sorted(),
                    "allowed_invoice_types": sorted(INVOICE_TYPE_TO_PK.keys()),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4

    print(json.dumps({"ok": True, "validated_count": len(data)}, ensure_ascii=False))
    return 0


def expense_keys_sorted() -> list[str]:
    return sorted(EXPENSE_ITEM_TO_PK.keys())


if __name__ == "__main__":
    raise SystemExit(main())
