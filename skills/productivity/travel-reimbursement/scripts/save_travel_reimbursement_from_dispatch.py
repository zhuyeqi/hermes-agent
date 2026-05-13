from __future__ import annotations

"""Build and submit the save payload for a travel reimbursement bill (差旅费报销单)."""

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from erm_common import (  # noqa: E402
    ERM_BASE_URL,
    add_common_args,
    make_client,
    parse_cookie_header,
    post_form,
    print_json,
)
from extract_dispatch_defaults import extract_defaults, load_dispatch_json  # noqa: E402

ZERO2 = "0.00"
ZERO8 = "0.00000000"

TRADE_TYPE = "264X-Cxx-CLBX"
PK_BILLTEMPLET_DEFAULT = "1001ZZ10000000007SVA"
TRAVEL_EXPENSE_PK = "1001A110000000001GO8"

VEHICLE_TO_PK: dict[str, str] = {
    "飞机（商务舱）": "1001C110000000006HLL",
    "飞机（经济舱）": "1001C110000000006HLN",
    "火车（商务座）": "1001A110000000002YRS",
    "火车（一等座）": "1001C110000000006HLO",
    "火车（二等座）": "1001A110000000002YRU",
    "出租车": "1001C110000000006HLP",
    "公交/地铁": "1001C110000000006HLQ",
    "长途巴士": "1001A110000000002YRX",
    "轮船": "1001A110000000002YRY",
    "其他": "1001A110000000002YS1",
}

INVOICE_FORM_TO_PK: dict[str, str] = {
    "飞机行程单": "1001W210000000022G8D",
    "火车电子报销凭证": "1001W210000000022G8E",
    "火车纸质报销凭证": "1001W210000000022G8F",
    "长途巴士、轮船、出租车报销凭证": "1001W210000000022G9C",
}

INVOICE_TYPE_TO_PK: dict[str, str] = {
    "增值税专用发票": "1001ZZ1000000000SQ9Z",
    "增值税普通发票": "1001ZZ1000000000SQA1",
}

CITY_TYPE_TO_PK: dict[str, str] = {
    "公司负责人/一般地区": "1001W21000000001ZEYR",
    "公司负责人/省会直辖市": "1001W21000000001ZEYS",
    "公司负责人/北京上海广深": "1001W21000000001ZEYT",
    "其他人员/一般地区": "1001W21000000001ZEYU",
    "其他人员/省会直辖市": "1001W21000000001ZEYV",
    "其他人员/北京上海广深": "1001W21000000001ZEYW",
}

TRIP_TOOL_TO_PK: dict[str, str] = {
    "火车": "1001C110000000006HN2",
    "火车（过夜）": "1001C110000000006HN3",
    "长途巴士": "1001C110000000006HN4",
    "轮船": "1001C110000000006HN5",
}

YES_NO_TO_PK: dict[str, str] = {
    "是": "1001W21000000001XGK2",
    "否": "1001W21000000001XGK3",
}

TRAINING_FEE_TO_PK: dict[str, str] = {
    "否": "1001ZZ1000000000Y8SJ",
}


def money2(value: Decimal | str) -> str:
    return f"{Decimal(str(value)):.2f}"


def money8(value: Decimal | str) -> str:
    return f"{Decimal(str(value)):.8f}"


def require(name: str, value: Any) -> str:
    if value in (None, ""):
        raise ValueError(f"missing required value: {name}")
    return str(value)


def lookup(name: str, mapping: dict[str, str], value: str | None) -> str:
    if not value:
        raise ValueError(f"missing {name}; supported: {', '.join(mapping)}")
    raw = str(value).strip()
    if raw in mapping:
        return mapping[raw]
    if len(raw) >= 16 and raw.isalnum():
        return raw
    raise ValueError(f"unsupported {name}: {raw!r}; supported: {', '.join(mapping)}")


def _row_count(items: dict[str, Any]) -> int:
    return (
        len(items.get("transports") or [])
        + len(items.get("hotels") or [])
        + len(items.get("subsidies") or [])
    )


def load_items_json(items: dict[str, Any]) -> dict[str, Any]:
    if _row_count(items) == 0:
        raise ValueError("items-json must contain at least one transports/hotels/subsidies entry")
    return items


def _build_transport_row(
    item: dict[str, Any],
    *,
    head: dict[str, Any],
    transport_defaults: dict[str, Any],
) -> tuple[dict[str, Any], Decimal]:
    amount = Decimal(str(require("transports[].amount", item.get("amount"))))
    receiver = item.get("receiver") or transport_defaults.get("receiver") or head["jkbxr"]
    skyhzh = item.get("bank_account") or transport_defaults.get("skyhzh") or head["skyhzh"]
    szxmid = item.get("expense_item_pk") or transport_defaults.get("szxmid") or TRAVEL_EXPENSE_PK
    bzbm = head["bzbm"]
    bbhl = head["bbhl"]

    departure = require("transports[].departure_date", item.get("departure_date"))
    arrival = require("transports[].arrival_date", item.get("arrival_date"))

    row = {
        "cls": "nc.vo.ep.bx.BXBusItemVO",
        "tablecode": "arap_bxbusitem",
        "paytarget": 0,
        "receiver": receiver,
        "skyhzh": skyhzh,
        "szxmid": szxmid,
        "dwbm": head["pk_org"],
        "deptid": head["deptid"],
        "jkbxr": head["jkbxr"],
        "bzbm": bzbm,
        "bbhl": bbhl,
        "defitem1": departure,
        "defitem2": arrival,
        "defitem5": lookup("transports[].vehicle", VEHICLE_TO_PK, item.get("vehicle")),
        "defitem15": lookup("transports[].invoice_form", INVOICE_FORM_TO_PK, item.get("invoice_form")),
        "defitem44": require("transports[].invoice_no", item.get("invoice_no")),
        "defitem46": money2(item.get("tax_amount", "0")),
        "defitem47": money2(amount),
        "defitem48": money2(item.get("tax_amount", "0")),
        "defitem50": money8(amount),
        "vat_amount": money2(amount),
        "tax_amount": ZERO8,
        "tni_amount": money2(amount),
        "amount": money2(amount),
        "bbje": money2(amount),
        "ybje": money2(amount),
        "zfybje": money8(amount),
        "zfbbje": money8(amount),
        "orgvat_amount": money2(amount),
        "orgtax_amount": ZERO8,
        "orgtni_amount": money2(amount),
        "hkbbje": ZERO8,
        "hkybje": ZERO8,
        "cjkybje": ZERO8,
        "cjkbbje": ZERO8,
        "groupbbje": ZERO8,
        "groupzfbbje": ZERO8,
        "grouphkbbje": ZERO8,
        "groupcjkbbje": ZERO8,
        "globalhkbbje": ZERO8,
        "globalzfbbje": ZERO8,
        "globalcjkbbje": ZERO8,
        "globalbbje": ZERO8,
        "grouptax_amount": ZERO2,
        "groupvat_amount": ZERO2,
        "grouptni_amount": ZERO2,
        "globaltax_amount": ZERO2,
        "globalvat_amount": ZERO2,
        "globaltni_amount": ZERO2,
        "groupbbhl": ZERO8,
        "globalbbhl": ZERO8,
    }
    return row, amount


def _build_hotel_row(
    item: dict[str, Any],
    *,
    head: dict[str, Any],
    hotel_defaults: dict[str, Any],
) -> tuple[dict[str, Any], Decimal]:
    amount = Decimal(str(require("hotels[].amount", item.get("amount"))))
    receiver = item.get("receiver") or hotel_defaults.get("receiver") or head["jkbxr"]
    skyhzh = item.get("bank_account") or hotel_defaults.get("skyhzh") or head["skyhzh"]
    szxmid = item.get("expense_item_pk") or hotel_defaults.get("szxmid") or TRAVEL_EXPENSE_PK

    row = {
        "cls": "nc.vo.ep.bx.BXBusItemVO",
        "tablecode": "other",
        "paytarget": 0,
        "receiver": receiver,
        "skyhzh": skyhzh,
        "szxmid": szxmid,
        "dwbm": head["pk_org"],
        "deptid": head["deptid"],
        "jkbxr": head["jkbxr"],
        "bzbm": head["bzbm"],
        "bbhl": head["bbhl"],
        "defitem16": lookup("hotels[].city_type", CITY_TYPE_TO_PK, item.get("city_type")),
        "defitem10": item.get("purpose", ""),
        "defitem20": str(require("hotels[].days", item.get("days"))),
        "defitem35": lookup("hotels[].invoice_type", INVOICE_TYPE_TO_PK, item.get("invoice_type")),
        "defitem44": require("hotels[].invoice_no", item.get("invoice_no")),
        "defitem22": money2(amount),
        "defitem46": money2(item.get("tax_amount", "0")),
        "vat_amount": money2(amount),
        "tax_amount": ZERO8,
        "tni_amount": money2(amount),
        "amount": money2(amount),
        "bbje": money2(amount),
        "ybje": money2(amount),
        "zfybje": money8(amount),
        "zfbbje": money8(amount),
        "orgvat_amount": money2(amount),
        "orgtax_amount": ZERO8,
        "orgtni_amount": money2(amount),
        "hkbbje": ZERO8,
        "hkybje": ZERO8,
        "cjkybje": ZERO8,
        "cjkbbje": ZERO8,
        "groupbbje": ZERO8,
        "groupzfbbje": ZERO8,
        "grouphkbbje": ZERO8,
        "groupcjkbbje": ZERO8,
        "globalhkbbje": ZERO8,
        "globalzfbbje": ZERO8,
        "globalcjkbbje": ZERO8,
        "globalbbje": ZERO8,
        "grouptax_amount": ZERO2,
        "groupvat_amount": ZERO2,
        "grouptni_amount": ZERO2,
        "globaltax_amount": ZERO2,
        "globalvat_amount": ZERO2,
        "globaltni_amount": ZERO2,
        "groupbbhl": ZERO8,
        "globalbbhl": ZERO8,
    }
    return row, amount


def _build_subsidy_row(
    item: dict[str, Any],
    *,
    head: dict[str, Any],
    subsidy_defaults: dict[str, Any],
) -> tuple[dict[str, Any], Decimal, dict[str, Any]]:
    days = Decimal(str(require("subsidies[].days", item.get("days"))))

    explicit_amount = item.get("amount")
    explicit_standard = item.get("standard")
    if explicit_amount not in (None, ""):
        amount = Decimal(str(explicit_amount))
        standard = (
            Decimal(str(explicit_standard))
            if explicit_standard not in (None, "")
            else (amount / days if days else Decimal("0"))
        )
        source = "items"
    else:
        if explicit_standard not in (None, ""):
            standard = Decimal(str(explicit_standard))
            source = "items"
        else:
            standard_value = subsidy_defaults.get("defitem11")
            if standard_value in (None, ""):
                raise ValueError(
                    "missing subsidy.defitem11 from dispatch defaults; provide subsidies[].standard or subsidies[].amount"
                )
            standard = Decimal(str(standard_value))
            source = "dispatch"
        amount = standard * days

    receiver = item.get("receiver") or subsidy_defaults.get("receiver") or head["jkbxr"]
    skyhzh = item.get("bank_account") or subsidy_defaults.get("skyhzh") or head["skyhzh"]

    row = {
        "cls": "nc.vo.ep.bx.BXBusItemVO",
        "tablecode": "bzitem",
        "paytarget": 0,
        "receiver": receiver,
        "skyhzh": skyhzh,
        "dwbm": head["pk_org"],
        "deptid": head["deptid"],
        "jkbxr": head["jkbxr"],
        "bzbm": head["bzbm"],
        "bbhl": head["bbhl"],
        "defitem11": money2(standard),
        "defitem9": str(days),
        "defitem40": lookup("subsidies[].tool", TRIP_TOOL_TO_PK, item.get("tool")),
        "defitem36": lookup("subsidies[].official_car_pickup", YES_NO_TO_PK, item.get("official_car_pickup")),
        "defitem37": lookup("subsidies[].hosted_by_counterparty", YES_NO_TO_PK, item.get("hosted_by_counterparty")),
        "vat_amount": money2(amount),
        "tax_amount": ZERO2,
        "tni_amount": money2(amount),
        "amount": money2(amount),
        "bbje": money2(amount),
        "ybje": money2(amount),
        "zfybje": ZERO8,
        "zfbbje": ZERO8,
        "orgvat_amount": money2(amount),
        "orgtax_amount": ZERO2,
        "orgtni_amount": money2(amount),
        "hkbbje": ZERO8,
        "hkybje": ZERO8,
        "cjkybje": ZERO8,
        "cjkbbje": ZERO8,
        "groupbbje": ZERO8,
        "groupzfbbje": ZERO8,
        "grouphkbbje": ZERO8,
        "groupcjkbbje": ZERO8,
        "globalhkbbje": ZERO8,
        "globalzfbbje": ZERO8,
        "globalcjkbbje": ZERO8,
        "globalbbje": ZERO8,
        "grouptax_amount": ZERO2,
        "groupvat_amount": ZERO2,
        "grouptni_amount": ZERO2,
        "globaltax_amount": ZERO2,
        "globalvat_amount": ZERO2,
        "globaltni_amount": ZERO2,
        "groupbbhl": ZERO8,
        "globalbbhl": ZERO8,
    }
    return row, amount, {"days": str(days), "standard": money2(standard), "amount": money2(amount), "standard_source": source}


def _resolve_head(
    args: argparse.Namespace,
    head_defaults: dict[str, Any],
    cookie: dict[str, str],
) -> dict[str, Any]:
    pk_org = head_defaults.get("pk_org") or cookie.get("user_org", "")
    pk_group = head_defaults.get("pk_group") or cookie.get("pk_unit", "") or cookie.get("pk_group", "")
    head = {
        "pk_org": require("head.pk_org", pk_org),
        "pk_org_v": require("head.pk_org_v", head_defaults.get("pk_org_v")),
        "pk_group": require("head.pk_group", pk_group),
        "pk_fiorg": head_defaults.get("pk_fiorg") or pk_org,
        "pk_tradetypeid": require("head.pk_tradetypeid", head_defaults.get("pk_tradetypeid")),
        "deptid": require("head.deptid", head_defaults.get("deptid")),
        "deptid_v": require(
            "head.deptid_v",
            head_defaults.get("deptid_v") or head_defaults.get("fydeptid_v"),
        ),
        "jkbxr": require("head.jkbxr", head_defaults.get("jkbxr")),
        "jkbxr_mobile": head_defaults.get("jkbxr_mobile") or "",
        "skyhzh": require("head.skyhzh", head_defaults.get("skyhzh")),
        "jsfs": require("head.jsfs", head_defaults.get("jsfs")),
        "bzbm": require("head.bzbm", head_defaults.get("bzbm")),
        "bbhl": str(head_defaults.get("bbhl") or "1.00000000"),
        "operator": head_defaults.get("operator") or cookie.get("userid", ""),
        "creator": head_defaults.get("creator") or cookie.get("userid", ""),
        "pk_payorg": head_defaults.get("pk_payorg") or pk_org,
        "pk_payorg_v": head_defaults.get("pk_payorg_v") or head_defaults.get("pk_org_v"),
        "fydwbm": head_defaults.get("fydwbm") or pk_org,
        "fydwbm_v": head_defaults.get("fydwbm_v") or head_defaults.get("pk_org_v"),
        "zyx16": head_defaults.get("zyx16") or "false",
        "zyx18": require("head.zyx18", head_defaults.get("zyx18")),
        "zyx20": require("head.zyx20", head_defaults.get("zyx20")),
    }
    return head


def build_save_form(
    args: argparse.Namespace,
    defaults: dict[str, Any],
    items: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    items = load_items_json(items)
    cookie = parse_cookie_header(args.cookie)
    head_defaults = defaults.get("head", {})
    head = _resolve_head(args, head_defaults, cookie)

    body_rows: list[dict[str, Any]] = []
    total = Decimal("0")
    non_subsidy_total = Decimal("0")

    for item in items.get("transports") or []:
        row, amount = _build_transport_row(item, head=head, transport_defaults=defaults.get("transport", {}))
        body_rows.append(row)
        total += amount
        non_subsidy_total += amount

    for item in items.get("hotels") or []:
        row, amount = _build_hotel_row(item, head=head, hotel_defaults=defaults.get("hotel", {}))
        body_rows.append(row)
        total += amount
        non_subsidy_total += amount

    subsidy_summaries: list[dict[str, Any]] = []
    for item in items.get("subsidies") or []:
        row, amount, summary = _build_subsidy_row(
            item, head=head, subsidy_defaults=defaults.get("subsidy", {})
        )
        body_rows.append(row)
        subsidy_summaries.append(summary)
        total += amount

    bill_date = items.get("bill_date") or datetime.now().strftime("%Y-%m-%d")
    djrq = f"{bill_date} 00:00:00"
    creationtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    invoice_row_count = len(items.get("transports") or []) + len(items.get("hotels") or [])
    fjzs = str(items.get("attachment_count") or invoice_row_count)

    training_fee_pk = head_defaults.get("zyx11")
    if items.get("training_fee_pk"):
        training_fee_pk = items["training_fee_pk"]
    elif items.get("training_fee"):
        training_fee_pk = lookup("items.training_fee", TRAINING_FEE_TO_PK, items["training_fee"])
    if not training_fee_pk:
        raise ValueError("missing head.zyx11; provide training_fee in items-json or default in dispatch")

    bill_head = {
        "djrq": djrq,
        "zy": require("items.summary", items.get("summary")),
        "zfbbje": money2(non_subsidy_total),
        "cjkbbje": ZERO8,
        "deptid": head["deptid"],
        "fydeptid_v": head["deptid_v"],
        "jkbxr": head["jkbxr"],
        "skyhzh": head["skyhzh"],
        "fjzs": fjzs,
        "jsfs": head["jsfs"],
        "deptid_v": head["deptid_v"],
        "bzbm": head["bzbm"],
        "bbhl": head["bbhl"],
        "vat_amount": money2(total),
        "total": money2(total),
        "dwbm": head["pk_org"],
        "fydeptid": head["deptid"],
        "jkbxr_mobile": head["jkbxr_mobile"],
        "pk_org_v": head["pk_org_v"],
        "selected": "N",
        "pk_org": head["pk_org"],
        "pk_tradetypeid": head["pk_tradetypeid"],
        "pk_group": head["pk_group"],
        "pk_fiorg": head["pk_fiorg"],
        "djlxbm": TRADE_TYPE,
        "bbje": money2(total),
        "ybje": money2(total),
        "zfybje": money2(non_subsidy_total),
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
        "operator": head["operator"],
        "dwbm_v": head["pk_org_v"],
        "isneedimag": "N",
        "isexpedited": "N",
        "pk_payorg_v": head["pk_payorg_v"],
        "pk_payorg": head["pk_payorg"],
        "fydwbm": head["fydwbm"],
        "fydwbm_v": head["fydwbm_v"],
        "zyx11": training_fee_pk,
        "zyx16": head["zyx16"],
        "zyx18": head["zyx18"],
        "zyx20": head["zyx20"],
        "paytarget": 0,
        "receiver": head["jkbxr"],
        "tax_amount": ZERO2,
        "tni_amount": money2(total),
        "orgtax_amount": ZERO2,
        "orgvat_amount": money2(total),
        "orgtni_amount": money2(total),
        "grouptax_amount": ZERO2,
        "groupvat_amount": ZERO2,
        "grouptni_amount": ZERO2,
        "globaltax_amount": ZERO2,
        "globalvat_amount": ZERO2,
        "globaltni_amount": ZERO2,
        "creator": head["creator"],
        "creationtime": creationtime,
    }

    save_form = {
        "tradetype": TRADE_TYPE,
        "pk_billtemplet": getattr(args, "pk_billtemplet", PK_BILLTEMPLET_DEFAULT) or PK_BILLTEMPLET_DEFAULT,
        "state": "add",
        "bill": json.dumps(
            {"head": bill_head, "body": {"bodys": body_rows}},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "accessorybillid": getattr(args, "accessorybillid", "") or "",
        "card_html": "jkbxcard",
    }

    resolved = {
        "summary": items.get("summary"),
        "bill_date": bill_date,
        "total": money2(total),
        "subsidies": subsidy_summaries,
        "training_fee_pk": training_fee_pk,
        "row_counts": {
            "transports": len(items.get("transports") or []),
            "hotels": len(items.get("hotels") or []),
            "subsidies": len(items.get("subsidies") or []),
        },
    }
    return save_form, resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Save a travel reimbursement bill (差旅费报销单) from dispatch defaults + items JSON."
    )
    add_common_args(parser)
    parser.add_argument("--dispatch-json", required=True, type=Path)
    parser.add_argument("--items-json", required=True, type=Path)
    parser.add_argument("--accessorybillid", default="")
    parser.add_argument("--pk-billtemplet", default=PK_BILLTEMPLET_DEFAULT)
    parser.add_argument("--save-form-out", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dispatch = load_dispatch_json(args.dispatch_json)
    defaults = extract_defaults(dispatch)
    items = json.loads(Path(args.items_json).read_text(encoding="utf-8"))

    save_form, resolved = build_save_form(args, defaults, items)

    if args.save_form_out:
        Path(args.save_form_out).write_text(
            json.dumps({"save_form": save_form, "resolved": resolved}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.dry_run:
        print_json({"ok": True, "mode": "dry_run", "resolved": resolved, "defaults": defaults, "save_form": save_form})
        return 0

    with make_client(args) as client:
        response = post_form(
            client,
            base_url=ERM_BASE_URL,
            path="/iwebap/jkbx_maintain_ctr/savebill",
            form=save_form,
        )

    print_json({"ok": True, "resolved": resolved, "response": response})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
