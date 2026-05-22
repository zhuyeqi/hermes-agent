from __future__ import annotations

import argparse
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

SCRIPT_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_LIB))
sys.path.insert(0, str(SCRIPT_DIR))

from save_travel_reimbursement_from_dispatch import build_save_form, load_items_json


DEFAULTS = {
    "head": {
        "pk_org": "ORG",
        "pk_group": "GROUP",
        "pk_org_v": "ORG_V",
        "pk_fiorg": "ORG",
        "dwbm": "ORG",
        "dwbm_v": "ORG_V",
        "pk_tradetypeid": "TRADE_ID",
        "deptid": "DEPT",
        "deptid_v": "DEPT_V",
        "fydeptid": "DEPT",
        "fydeptid_v": "DEPT_V",
        "jkbxr": "USER",
        "jkbxr_mobile": "13800000000",
        "receiver": "USER",
        "skyhzh": "BANK",
        "jsfs": "SETTLEMENT",
        "bzbm": "CNY",
        "bbhl": "1.00000000",
        "pk_payorg": "ORG",
        "pk_payorg_v": "ORG_V",
        "fydwbm": "ORG",
        "fydwbm_v": "ORG_V",
        "zyx11": "TRAINING_NO_DEFAULT",
        "zyx18": "Z18",
        "zyx20": "Z20",
    },
    "transport": {
        "receiver": "USER",
        "skyhzh": "BANK",
        "szxmid": "TRAVEL_EXPENSE_DEFAULT",
        "dwbm": "ORG",
        "deptid": "DEPT",
        "jkbxr": "USER",
        "bzbm": "CNY",
        "bbhl": "1.00000000",
    },
    "hotel": {
        "receiver": "USER",
        "skyhzh": "BANK",
        "szxmid": "TRAVEL_EXPENSE_DEFAULT",
        "dwbm": "ORG",
        "deptid": "DEPT",
        "jkbxr": "USER",
        "bzbm": "CNY",
        "bbhl": "1.00000000",
    },
    "subsidy": {
        "receiver": "USER",
        "skyhzh": "BANK",
        "defitem11": "200.00",
        "dwbm": "ORG",
        "deptid": "DEPT",
        "jkbxr": "USER",
        "bzbm": "CNY",
        "bbhl": "1.00000000",
    },
}

ITEMS = {
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
        },
        {
            "departure_date": "2026-05-11",
            "arrival_date": "2026-05-22",
            "vehicle": "飞机（经济舱）",
            "invoice_form": "飞机行程单",
            "invoice_no": "F456",
            "amount": "600.00",
        },
    ],
    "hotels": [
        {
            "city_type": "其他人员/省会直辖市",
            "purpose": "住宿",
            "days": 2,
            "invoice_type": "增值税普通发票",
            "invoice_no": "H789",
            "amount": "600.00",
            "tax_amount": "0.00",
        }
    ],
    "subsidies": [
        {
            "days": 2,
            "tool": "火车",
            "official_car_pickup": "否",
            "hosted_by_counterparty": "否",
        }
    ],
}


def args(**overrides: str) -> argparse.Namespace:
    base = {
        "cookie": "userid=OPERATOR; user_org=ORG; pk_unit=GROUP",
        "accessorybillid": "ACCESSORY",
        "pk_billtemplet": "1001ZZ10000000007SVA",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class SaveTravelReimbursementTest(unittest.TestCase):
    def test_build_save_form_creates_multi_table_body_and_dynamic_subsidy(self) -> None:
        save_form, resolved = build_save_form(args(), DEFAULTS, ITEMS)
        bill = json.loads(save_form["bill"])

        self.assertEqual(save_form["tradetype"], "264X-Cxx-CLBX")
        self.assertEqual(save_form["accessorybillid"], "ACCESSORY")
        self.assertEqual(bill["head"]["zy"], "北京出差")
        self.assertEqual(bill["head"]["djlxbm"], "264X-Cxx-CLBX")
        self.assertEqual(bill["head"]["vat_amount"], "2100.00")
        self.assertEqual(bill["head"]["fjzs"], "3")

        rows = bill["body"]["bodys"]
        self.assertEqual([row["tablecode"] for row in rows], ["arap_bxbusitem", "arap_bxbusitem", "other", "bzitem"])
        self.assertEqual(rows[0]["defitem5"], "1001A110000000002YRU")
        self.assertEqual(rows[0]["defitem15"], "1001W210000000022G8E")
        self.assertEqual(rows[2]["defitem35"], "1001ZZ1000000000SQA1")
        self.assertEqual(rows[3]["defitem11"], "200.00")
        self.assertEqual(rows[3]["vat_amount"], "400.00")
        self.assertEqual(resolved["subsidies"][0]["standard_source"], "dispatch")

    def test_build_save_form_requires_dynamic_subsidy_standard(self) -> None:
        defaults = json.loads(json.dumps(DEFAULTS))
        defaults["subsidy"].pop("defitem11")

        with self.assertRaises(ValueError) as ctx:
            build_save_form(args(), defaults, ITEMS)

        self.assertIn("subsidy.defitem11", str(ctx.exception))

    def test_load_items_json_requires_one_body_row(self) -> None:
        with self.assertRaises(ValueError):
            load_items_json({"summary": "empty", "transports": [], "hotels": [], "subsidies": []})


if __name__ == "__main__":
    unittest.main()
