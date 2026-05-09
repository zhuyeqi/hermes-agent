from __future__ import annotations

"""Extract system-managed savebill defaults from an ERM dispatch response.

Use this after opening the reimbursement add page in the browser and saving
the latest /iwebap/evt/dispatch response body or an observed network JSONL.
"""

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
    "zyx16",
    "zyx18",
    "zyx20",
)

BODY_FIELDS = (
    "receiver",
    "skyhzh",
    "dwbm",
    "deptid",
    "jkbxr",
    "bzbm",
    "bbhl",
    "defitem13",
    "paytarget",
)


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def pick_from_table(table: dict[str, Any], field: str) -> Any:
    rows = table.get("rows") or []
    if rows:
        data = (rows[0] or {}).get("data") or {}
        if field in data:
            value = unwrap(data[field])
            if value not in (None, ""):
                return value
    meta = table.get("meta") or {}
    if field in meta:
        value = meta[field].get("default")
        if value not in (None, ""):
            return value
    return None


def load_dispatch_json(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if "dataTables" in data:
        return data
    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, str):
        decoded = json.loads(body)
        if "dataTables" in decoded:
            return decoded
    response = data.get("response") if isinstance(data, dict) else None
    if isinstance(response, dict) and isinstance(response.get("body"), str):
        decoded = json.loads(response["body"])
        if "dataTables" in decoded:
            return decoded
    raise ValueError("input must be dispatch JSON, observed JSONL object, or object with response.body")


def load_latest_dispatch_from_jsonl(path: str) -> dict[str, Any]:
    latest: dict[str, Any] | None = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "/iwebap/evt/dispatch" not in line:
            continue
        obj = json.loads(line)
        response = obj.get("response") or {}
        body = response.get("body")
        if not isinstance(body, str):
            continue
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            # Some exported capture lines may be truncated; skip them.
            continue
        if "dataTables" in decoded:
            latest = decoded
    if latest is None:
        raise ValueError(f"no dispatch response found in {path}")
    return latest


def extract_defaults(dispatch: dict[str, Any]) -> dict[str, Any]:
    tables = dispatch.get("dataTables") or {}
    head = tables.get("headform") or {}
    body = (
        tables.get("body_1arap_bxbusitem")
        or tables.get("body_1bzitem")
        or tables.get("body_1zsitem")
        or {}
    )

    head_defaults: dict[str, Any] = {}
    for field in HEAD_FIELDS:
        value = pick_from_table(head, field)
        if value not in (None, ""):
            head_defaults[field] = value

    body_defaults: dict[str, Any] = {}
    for field in BODY_FIELDS:
        value = pick_from_table(body, field)
        if value not in (None, ""):
            body_defaults[field] = value

    # defitem13 is a body-row default in the captured ERM model.
    if "defitem13" not in body_defaults:
        for table_name in ("body_1arap_bxbusitem", "body_1bzitem", "body_1zsitem"):
            value = pick_from_table(tables.get(table_name) or {}, "defitem13")
            if value not in (None, ""):
                body_defaults["defitem13"] = value
                break

    return {
        "head": head_defaults,
        "body": body_defaults,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract system defaults from ERM dispatch response.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dispatch-json", help="File containing raw dispatch JSON or observed object")
    source.add_argument("--observed-jsonl", help="JSONL capture; latest dispatch response will be used")
    args = parser.parse_args()

    dispatch = (
        load_dispatch_json(args.dispatch_json)
        if args.dispatch_json
        else load_latest_dispatch_from_jsonl(args.observed_jsonl)
    )
    defaults = extract_defaults(dispatch)
    missing = {
        "head": [field for field in HEAD_FIELDS if field not in defaults["head"]],
        "body": [field for field in BODY_FIELDS if field not in defaults["body"]],
    }
    print_json({"defaults": defaults, "missing": missing})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
