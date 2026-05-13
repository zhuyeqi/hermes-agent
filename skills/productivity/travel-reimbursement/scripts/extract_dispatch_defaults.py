from __future__ import annotations

"""Extract default field values from a dispatch response for travel reimbursement."""

import argparse
import json
from pathlib import Path
from typing import Any

from erm_common import print_json

HEAD_FIELDS = (
    "pk_org",
    "pk_group",
    "pk_org_v",
    "pk_fiorg",
    "dwbm",
    "dwbm_v",
    "pk_tradetypeid",
    "operator",
    "creator",
    "creationtime",
    "deptid",
    "deptid_v",
    "fydeptid",
    "fydeptid_v",
    "jkbxr",
    "jkbxr_mobile",
    "receiver",
    "skyhzh",
    "jsfs",
    "bzbm",
    "bbhl",
    "pk_payorg",
    "pk_payorg_v",
    "fydwbm",
    "fydwbm_v",
    "zyx11",
    "zyx16",
    "zyx18",
    "zyx20",
)

TRANSPORT_FIELDS = (
    "receiver",
    "skyhzh",
    "szxmid",
    "defitem1",
    "defitem2",
    "defitem5",
    "defitem15",
    "defitem44",
    "vat_amount",
    "defitem47",
    "defitem48",
    "defitem46",
    "dwbm",
    "deptid",
    "jkbxr",
    "bzbm",
    "bbhl",
    "paytarget",
)

HOTEL_FIELDS = (
    "receiver",
    "skyhzh",
    "szxmid",
    "defitem16",
    "defitem10",
    "defitem20",
    "defitem22",
    "defitem35",
    "defitem44",
    "defitem46",
    "vat_amount",
    "dwbm",
    "deptid",
    "jkbxr",
    "bzbm",
    "bbhl",
    "paytarget",
)

SUBSIDY_FIELDS = (
    "receiver",
    "skyhzh",
    "defitem11",
    "defitem9",
    "defitem40",
    "defitem36",
    "defitem37",
    "vat_amount",
    "dwbm",
    "deptid",
    "jkbxr",
    "bzbm",
    "bbhl",
    "paytarget",
)


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def row_data(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("data") or row.get("values") or {}


def pick_from_table(table: dict[str, Any], field: str) -> Any:
    rows = table.get("rows") or []
    if rows:
        data = row_data(rows[0] or {})
        if field in data:
            value = unwrap(data[field])
            if value not in (None, ""):
                return value
    meta = table.get("meta") or {}
    if field in meta:
        default = meta[field]
        value = unwrap(default.get("default") if isinstance(default, dict) else default)
        if value not in (None, ""):
            return value
    return None


def extract_table_defaults(table: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for field in fields:
        value = pick_from_table(table, field)
        if value not in (None, ""):
            defaults[field] = value
    return defaults


def load_dispatch_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "dataTables" in data:
        return data
    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, str):
        decoded = json.loads(body)
        if isinstance(decoded, dict) and "dataTables" in decoded:
            return decoded
    response = data.get("response") if isinstance(data, dict) else None
    if isinstance(response, dict) and isinstance(response.get("body"), str):
        decoded = json.loads(response["body"])
        if isinstance(decoded, dict) and "dataTables" in decoded:
            return decoded
    raise ValueError("input must be dispatch JSON, observed JSONL object, or object with response.body")


def extract_defaults(dispatch: dict[str, Any]) -> dict[str, Any]:
    data_tables = dispatch.get("dataTables", {})
    head_table = data_tables.get("headform") or data_tables.get("head") or {}
    transport_table = data_tables.get("body_1arap_bxbusitem") or {}
    hotel_table = data_tables.get("body_1other") or {}
    subsidy_table = data_tables.get("body_1bzitem") or {}

    return {
        "head": extract_table_defaults(head_table, HEAD_FIELDS),
        "transport": extract_table_defaults(transport_table, TRANSPORT_FIELDS),
        "hotel": extract_table_defaults(hotel_table, HOTEL_FIELDS),
        "subsidy": extract_table_defaults(subsidy_table, SUBSIDY_FIELDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract default values from dispatch JSON for travel reimbursement."
    )
    parser.add_argument(
        "--dispatch-json", required=True, type=Path, help="Path to dispatch.json"
    )
    args = parser.parse_args()

    dispatch = load_dispatch_json(args.dispatch_json)
    defaults = extract_defaults(dispatch)
    print_json({"defaults": defaults})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
