from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from extract_dispatch_defaults import extract_defaults, load_dispatch_json


def cell(value: str) -> dict[str, str]:
    return {"value": value}


def table(data: dict[str, str]) -> dict:
    return {"rows": [{"data": {key: cell(value) for key, value in data.items()}}]}


class ExtractDispatchDefaultsTest(unittest.TestCase):
    def test_extract_defaults_reads_travel_tables(self) -> None:
        dispatch = {
            "dataTables": {
                "headform": table(
                    {
                        "pk_org": "ORG",
                        "pk_org_v": "ORG_V",
                        "deptid": "DEPT",
                        "deptid_v": "DEPT_V",
                        "jkbxr": "USER",
                        "skyhzh": "BANK",
                        "jsfs": "SETTLEMENT",
                        "zyx11": "TRAINING_NO",
                        "pk_tradetypeid": "TRADE_ID",
                        "bzbm": "CNY",
                        "bbhl": "1.00000000",
                    }
                ),
                "body_1arap_bxbusitem": table(
                    {
                        "receiver": "USER",
                        "skyhzh": "BANK",
                        "szxmid": "TRAVEL_EXPENSE",
                        "defitem5": "TRAIN",
                        "defitem15": "TRAIN_INVOICE",
                        "vat_amount": "0.00",
                    }
                ),
                "body_1other": table(
                    {
                        "receiver": "USER",
                        "skyhzh": "BANK",
                        "defitem16": "CITY_TYPE",
                        "defitem20": "2",
                        "defitem35": "VAT_NORMAL",
                    }
                ),
                "body_1bzitem": table(
                    {
                        "receiver": "USER",
                        "skyhzh": "BANK",
                        "defitem11": "200.00",
                        "defitem40": "TRAIN_TOOL",
                        "defitem36": "NO",
                        "defitem37": "NO",
                    }
                ),
            }
        }

        defaults = extract_defaults(dispatch)

        self.assertEqual(defaults["head"]["pk_org"], "ORG")
        self.assertEqual(defaults["head"]["zyx11"], "TRAINING_NO")
        self.assertEqual(defaults["transport"]["defitem5"], "TRAIN")
        self.assertEqual(defaults["hotel"]["defitem16"], "CITY_TYPE")
        self.assertEqual(defaults["subsidy"]["defitem11"], "200.00")

    def test_load_dispatch_json_reads_response_body_wrapper(self) -> None:
        wrapped = {"response": {"body": json.dumps({"dataTables": {"headform": {}}})}}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dispatch_detail.json"
            path.write_text(json.dumps(wrapped), encoding="utf-8")

            self.assertEqual(load_dispatch_json(path)["dataTables"], {"headform": {}})


if __name__ == "__main__":
    unittest.main()
