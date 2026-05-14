from __future__ import annotations

"""Build and save a general reimbursement bill from dispatch defaults plus invoice fields.

Normal path:
1. Get Cookie from browser after login.
2. Open the add page and save the latest /iwebap/evt/dispatch response.
3. Optionally upload attachments first and pass --accessorybillid.
4. Run this script with invoice amount, tax, expense item, invoice type, and invoice number.
"""

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from erm_common import ERM_BASE_URL

ZERO8 = "0.00000000"
TRADE_TYPE = "264X-Cxx-TYBXD"

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

INVOICE_TYPE_TO_PK: dict[str, str] = {
    "增值税专用发票": "1001ZZ1000000000SQ9Z",
    "增值税普通发票": "1001ZZ1000000000SQA1",
}

EXPENSE_ITEM_TO_PK: dict[str, str] = {
    "业务招待费": "1001A110000000001GO7",
    "中介机构费用-其它": "1001A110000000001GPF",
    "中介机构费用-审计费": "1001A110000000001GPC",
    "中介机构费用-律师代理费": "1001A110000000001GPE",
    "中介机构费用-评估费": "1001A110000000001GPD",
    "中介机构费用-评审费": "1001A110000000001GPB",
    "交通费-公务交通费": "1001A110000000001GPX",
    "交通费-车辆运营使用费": "1001A110000000001GPQ",
    "会议费": "1001A110000000001GOB",
    "低值易耗品-IT类": "1001A110000000002UWV",
    "低值易耗品-其他": "1001A110000000002UWW",
    "保险费": "1001A110000000001GS2",
    "修理费": "1001A110000000001GO6",
    "党建工作经费": "1001A110000000001GRX",
    "其他应付款-其他": "1001A110000000002YN1",
    "其他应收款": "1001A110000000001GOU",
    "出国人员经费": "1001A110000000001GOZ",
    "办公费-信息化运维费": "1001A110000000001GPL",
    "办公费-信息资讯费": "1001A110000000001GPO",
    "办公费-其他": "1001A110000000001GPI",
    "办公费-办公用品": "1001A110000000001GPH",
    "办公费-印刷费": "1001A110000000001GS6",
    "办公费-报刊费": "1001A110000000001GPK",
    "办公费-电话费": "1001A110000000001GPM",
    "办公费-网络费": "1001A110000000001GPJ",
    "办公费-邮寄费": "1001A110000000001GPN",
    "咨询费": "1001A110000000001GOC",
    "固定资产-硬件设备": "1001A110000000001GOJ",
    "固定资产-运输设备": "1001A110000000001GOI",
    "固定资产-非生产管理用工设备及器具": "1001A110000000001GOH",
    "外部劳务费": "1001A110000000001GOF",
    "宣传费": "1001A110000000001GO9",
    "差旅费": "1001A110000000001GO8",
    "无形资产": "1001A110000000001GOX",
    "水费": "1001A110000000001GOW",
    "物业管理费": "1001A110000000001GOE",
    "电费": "1001A110000000001GOA",
    "研究与发展费": "1001A110000000001GS5",
    "研究与开发费": "1001A110000000001GOY",
    "租赁费": "1001A110000000001GOD",
    "职工薪酬-住房公积金": "1001A110000000001I9J",
    "职工薪酬-住房费用": "1001A110000000001I9I",
    "职工薪酬-工会经费": "1001A110000000001GP1",
    "职工薪酬-工资-企业负责人薪酬": "1001A110000000002YMR",
    "职工薪酬-工资-员工工资": "1001A110000000002YMQ",
    "职工薪酬-社会保险费用-其他": "1001A110000000002YN0",
    "职工薪酬-社会保险费用-基本养老保险": "1001A110000000002YMT",
    "职工薪酬-社会保险费用-基本医疗保险": "1001A110000000002YMV",
    "职工薪酬-社会保险费用-失业保险": "1001A110000000002YMX",
    "职工薪酬-社会保险费用-工伤保险": "1001A110000000002YMY",
    "职工薪酬-社会保险费用-生育保险": "1001A110000000002YMZ",
    "职工薪酬-社会保险费用-补充养老保险（企业年金）": "1001A110000000002YMU",
    "职工薪酬-社会保险费用-补充医疗保险": "1001A110000000002YMW",
    "职工薪酬-福利费用-供暖费": "1001A110000000001GP8",
    "职工薪酬-福利费用-公用药费": "1001A110000000001GP4",
    "职工薪酬-福利费用-其他": "1001A110000000001GP7",
    "职工薪酬-福利费用-理发费": "1001W21000000001MX71",
    "职工薪酬-福利费用-职工体检费": "1001A110000000001GP6",
    "职工薪酬-福利费用-职工食堂": "1001A110000000001GP9",
    "职工薪酬-福利费用-防暑降温费": "1001A110000000001GP5",
    "职工薪酬-职工教育经费": "1001A110000000001GP2",
    "职工薪酬-雇主责任保险费": "1001A110000000001GO5",
    "董事会费": "1001A110000000001GOV",
    "诉讼费": "1001A110000000001GS3",
    "金融机构手续费": "1001A110000000001ZN1",
}


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in cookie_header.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def post_form(
    client: httpx.Client,
    *,
    base_url: str,
    path: str,
    form: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        join_url(base_url, path),
        data=form,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
    )
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return json.loads(response.text)


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


def money(value: str, places: int) -> str:
    return f"{Decimal(value):.{places}f}"


def resolve_invoice_type_pk(name: str, override_pk: str = "") -> str:
    if override_pk.strip():
        return override_pk.strip()
    pk = INVOICE_TYPE_TO_PK.get(name.strip())
    if not pk:
        raise ValueError(f"unsupported invoice type: {name!r}; supported={', '.join(INVOICE_TYPE_TO_PK)}")
    return pk


def resolve_expense_item_pk(name: str, override_pk: str = "") -> str:
    if override_pk.strip():
        return override_pk.strip()
    pk = EXPENSE_ITEM_TO_PK.get(name.strip())
    if not pk:
        raise ValueError(f"unsupported expense item: {name!r}; supported={', '.join(EXPENSE_ITEM_TO_PK)}")
    return pk


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


def require_value(name: str, value: str | None) -> str:
    if value in (None, ""):
        raise SystemExit(f"missing system field {name}; verify --dispatch-json or pass explicit override")
    return str(value)


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


def build_save_form(args: argparse.Namespace, defaults: dict[str, Any], invoices: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
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

    shared: dict[str, Any] = {
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
        # Attachment upload entrypoint is preserved:
        # external uploader can provide/accessory bill id and reuse this script.
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
        "invoices": [
            {
                "expense_item": {"name": inv["expense_item"], "pk": resolve_expense_item_pk(inv["expense_item"])},
                "invoice_type": {"name": inv["invoice_type"], "pk": resolve_invoice_type_pk(inv["invoice_type"])},
                "invoice_no": inv["invoice_no"],
            }
            for inv in invoices
        ],
    }
    return save_form, resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-file save flow: dispatch-json defaults + payload build + savebill post."
    )
    parser.add_argument("--cookie", required=True, help="Raw Cookie header copied from browser")
    parser.add_argument("--timeout", type=float, default=30.0)

    parser.add_argument("--dispatch-json", required=True, help="Full dispatch JSON / observed object JSON")
    parser.add_argument("--pk-org", default="", help="Defaults to dispatch head.pk_org or cookie user_org")
    parser.add_argument("--pk-group", default="", help="Defaults to dispatch head.pk_group or cookie pk_unit")
    parser.add_argument("--pk-org-v", default="", help="Override if dispatch value cannot be used")
    parser.add_argument("--pk-fiorg", default="")
    parser.add_argument("--pk-tradetypeid", default="")
    parser.add_argument("--jkbxr-mobile", default="")
    parser.add_argument("--operator", default="", help="Defaults to cookie userid")
    parser.add_argument("--creator", default="", help="Defaults to cookie userid")
    parser.add_argument("--bzbm", default="")
    parser.add_argument("--zyx18", default="")
    parser.add_argument("--zyx20", default="")
    parser.add_argument("--bill-date", default="")
    parser.add_argument("--zy", required=True)
    parser.add_argument("--invoices-json", required=True, help="Path to JSON file containing invoice array")
    parser.add_argument("--deptid", default="")
    parser.add_argument("--deptid-v", default="")
    parser.add_argument("--jkbxr", default="")
    parser.add_argument("--skyhzh", default="")
    parser.add_argument("--jsfs", default="")
    parser.add_argument("--defitem13", default="", help="Override body.defitem13 if needed")
    parser.add_argument("--accessorybillid", default="", help="Attachment bill id entrypoint; uploader can fill this")
    parser.add_argument("--attachment-manifest-json", default="", help="Reserved entrypoint for attachment uploader integration")
    parser.add_argument("--pk-billtemplet", default="1001Q110000000000SSG")
    parser.add_argument("--save-form-out", default="", help="Optional output path for generated save_form JSON")
    parser.add_argument("--dry-run", action="store_true", help="Only build payload, do not post savebill")
    args = parser.parse_args()

    dispatch = load_dispatch_json(args.dispatch_json)
    defaults = extract_defaults(dispatch)
    invoices = load_invoices(args.invoices_json)
    save_form, resolved = build_save_form(args, defaults, invoices)

    if args.save_form_out:
        out_path = Path(args.save_form_out)
        out_path.write_text(json.dumps({"save_form": save_form}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.dry_run:
        print_json(
            {
                "ok": True,
                "mode": "dry_run",
                "resolved": resolved,
                "defaults": defaults,
                "save_form": save_form,
                "attachment": {
                    "accessorybillid": args.accessorybillid,
                    "attachment_manifest_json": args.attachment_manifest_json,
                },
            }
        )
        return 0

    import httpx

    with httpx.Client(headers={"Cookie": args.cookie}, timeout=args.timeout, follow_redirects=True) as client:
        out = post_form(
            client,
            base_url=ERM_BASE_URL,
            path="/iwebap/jkbx_maintain_ctr/savebill",
            form=save_form,
        )

    print_json(
        {
            "ok": True,
            "resolved": resolved,
            "defaults": defaults,
            "attachment": {
                "accessorybillid": args.accessorybillid,
                "attachment_manifest_json": args.attachment_manifest_json,
            },
            "response": out,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
