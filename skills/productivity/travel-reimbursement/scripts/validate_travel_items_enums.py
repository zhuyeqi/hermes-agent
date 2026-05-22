"""Validate ITEMS_JSON enum fields against ERM travel dictionaries (preflight only)."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parent / "lib"
_SCRIPTS = Path(__file__).resolve().parent
for _p in (_LIB, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from erm_travel_enums import (  # noqa: E402
    CITY_TYPE_TO_PK,
    INVOICE_FORM_TO_PK,
    INVOICE_TYPE_ALIASES,
    INVOICE_TYPE_TO_PK,
    TRAINING_FEE_TO_PK,
    TRIP_TOOL_TO_PK,
    VEHICLE_TO_PK,
    YES_NO_TO_PK,
)


def suggest(value: str, allowed: list[str], n: int = 5) -> list[str]:
    return difflib.get_close_matches(value, allowed, n=n, cutoff=0.45)


def _check_enum(
    issues: list[dict[str, Any]],
    *,
    category: str,
    index: int,
    field: str,
    value: str,
    mapping: dict[str, str],
    aliases: dict[str, str] | None = None,
) -> None:
    raw = value.strip()
    if not raw:
        return
    if raw in mapping:
        return
    if len(raw) >= 16 and raw.isalnum():
        return
    entry: dict[str, Any] = {
        "category": category,
        "index": index,
        "field": field,
        "value": raw,
        "error_code": "items_enum_invalid",
        "message": f"{category}[{index}].{field} 不在系统字典中: {raw!r}",
        "suggestions": suggest(raw, sorted(mapping.keys())),
        f"allowed_{field}": sorted(mapping.keys()),
    }
    if aliases and raw in aliases:
        entry["hint"] = f"请改为字典精确名称: {aliases[raw]!r}（勿使用别名 {raw!r}）"
    issues.append(entry)


def validate_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    training = data.get("training_fee")
    if training is not None and str(training).strip():
        _check_enum(
            issues,
            category="items",
            index=0,
            field="training_fee",
            value=str(training),
            mapping=TRAINING_FEE_TO_PK,
        )

    for i, item in enumerate(data.get("transports") or []):
        if not isinstance(item, dict):
            continue
        _check_enum(
            issues,
            category="transports",
            index=i,
            field="vehicle",
            value=str(item.get("vehicle", "")),
            mapping=VEHICLE_TO_PK,
        )
        _check_enum(
            issues,
            category="transports",
            index=i,
            field="invoice_form",
            value=str(item.get("invoice_form", "")),
            mapping=INVOICE_FORM_TO_PK,
        )

    for i, item in enumerate(data.get("hotels") or []):
        if not isinstance(item, dict):
            continue
        _check_enum(
            issues,
            category="hotels",
            index=i,
            field="city_type",
            value=str(item.get("city_type", "")),
            mapping=CITY_TYPE_TO_PK,
        )
        _check_enum(
            issues,
            category="hotels",
            index=i,
            field="invoice_type",
            value=str(item.get("invoice_type", "")),
            mapping=INVOICE_TYPE_TO_PK,
            aliases=INVOICE_TYPE_ALIASES,
        )

    for i, item in enumerate(data.get("subsidies") or []):
        if not isinstance(item, dict):
            continue
        _check_enum(
            issues,
            category="subsidies",
            index=i,
            field="tool",
            value=str(item.get("tool", "")),
            mapping=TRIP_TOOL_TO_PK,
        )
        _check_enum(
            issues,
            category="subsidies",
            index=i,
            field="official_car_pickup",
            value=str(item.get("official_car_pickup", "")),
            mapping=YES_NO_TO_PK,
        )
        _check_enum(
            issues,
            category="subsidies",
            index=i,
            field="hosted_by_counterparty",
            value=str(item.get("hosted_by_counterparty", "")),
            mapping=YES_NO_TO_PK,
        )

    return issues


def main() -> int:
    p = argparse.ArgumentParser(description="Validate ITEMS_JSON enums before login/pipeline")
    p.add_argument("--items-json", required=True)
    args = p.parse_args()

    path = Path(args.items_json)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "items_json_invalid",
                    "message": str(e),
                    "hint": "修复 ITEMS_JSON 后重新运行 preflight_check.sh",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4

    if not isinstance(data, dict):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "items_json_invalid",
                    "message": "items-json must be a JSON object",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4

    issues = validate_items(data)
    if issues:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": "items_enum_invalid",
                    "message": f"{len(issues)} items field(s) not in ERM dictionary",
                    "hint": "修正 ITEMS_JSON：枚举字段须与 scripts/lib/erm_travel_enums.py 的 key 完全一致",
                    "issues": issues,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4

    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
