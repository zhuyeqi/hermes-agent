from __future__ import annotations

"""Upload a reimbursement attachment and return the accessorybillid.

The returned accessorybillid must be passed to save_general_reimbursement_from_dispatch.py
so the saved bill is linked to the uploaded file.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from erm_common import add_common_args, join_url, make_client, print_json  # noqa: E402

if TYPE_CHECKING:
    import httpx


TRADE_TYPE = "264X-Cxx-TYBXD"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_pk_bill(text: str) -> str:
    """
    generatBillId response shape varies across tenants and ERM versions:
    - JSON: {"pk_bill":"..."} / {"data":"..."} / {"billid":"..."}
    - Plain text: the pk_bill value itself
    """
    raw = text.strip()
    if not raw:
        return ""

    try:
        data = json.loads(raw)
    except Exception:
        data = None

    if isinstance(data, dict):
        for k in ("pk_bill", "billid", "id", "data", "value"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    m = re.search(r"\b[0-9A-Za-z]{16,}\b", raw)
    return m.group(0) if m else ""


def generat_bill_id(
    client: "httpx.Client",
    *,
    base_url: str,
    billtype: str = TRADE_TYPE,
    pk_bill: str = "undefined",
    t_ms: int | None = None,
) -> str:
    t = _now_ms() if t_ms is None else int(t_ms)
    url = join_url(
        base_url,
        f"/iwebap/erm_accessory_ctr/generatBillId?pk_bill={pk_bill}&billtype={billtype}&time={t}",
    )
    r = client.get(url, headers={"X-Requested-With": "XMLHttpRequest", "Accept": "*/*"})
    r.raise_for_status()
    pk = _parse_pk_bill(r.text)
    if not pk:
        raise RuntimeError(f"generatBillId returned unexpected body: {r.text!r}")
    return pk


def _saveaccessory_path(pk_bill: str, state: str) -> str:
    return f"/iwebap/erm_accessory_ctr/saveaccessory?pk_bill={pk_bill}&state={state}"


def _assert_upload_succeeded(*, filename: str, response_text: str) -> None:
    body = response_text or ""
    if "Request method POST not supported" in body:
        raise RuntimeError("saveaccessory rejected POST (wrong URL or method)")
    if "上传失败" in body:
        raise RuntimeError(f"server reported upload failure; response snippet: {body[:500]!r}")
    # Success HTML lists the file name in the table (observed capture).
    if filename and filename not in body:
        raise RuntimeError(
            f"upload response did not contain uploaded file name {filename!r}; "
            "check cookie/session or server message in response body"
        )


def upload_accessory_file(
    client: "httpx.Client",
    *,
    base_url: str,
    pk_bill: str,
    file_path: str,
    state: str = "add",
) -> dict[str, str | int]:
    """
    POST multipart/form-data to fixed saveaccessory URL; form field name is 'file'.
    Do not set Content-Type manually; httpx adds the multipart boundary.
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(str(p))

    path = _saveaccessory_path(pk_bill, state)
    upload_url = join_url(base_url, path)

    with p.open("rb") as f:
        files = {"file": (p.name, f, "application/octet-stream")}
        r = client.post(upload_url, files=files, headers={"Accept": "text/html,*/*"})
    r.raise_for_status()
    _assert_upload_succeeded(filename=p.name, response_text=r.text)

    return {
        "saveaccessory_path": path,
        "status_code": r.status_code,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="generatBillId → POST file to erm_accessory_ctr/saveaccessory (field name: file)."
    )
    add_common_args(ap)
    ap.add_argument("--billtype", default=TRADE_TYPE)
    ap.add_argument(
        "--pk-bill",
        default="",
        help="If set, skip generatBillId; this value is also accessorybillid for savebill.",
    )
    ap.add_argument(
        "--file",
        required=True,
        help="Local file to upload.",
    )
    ap.add_argument("--state", default="add")
    ap.add_argument("--time-ms", default="", help="Override time=... for generatBillId only (ms)")
    args = ap.parse_args()

    t_ms = int(args.time_ms) if str(args.time_ms).strip() else None
    with make_client(args) as client:
        pk_bill = args.pk_bill.strip() or generat_bill_id(
            client,
            base_url=args.base_url,
            billtype=args.billtype,
            pk_bill="undefined",
            t_ms=t_ms,
        )
        upload_info = upload_accessory_file(
            client,
            base_url=args.base_url,
            pk_bill=pk_bill,
            file_path=args.file,
            state=args.state,
        )

    print_json(
        {
            "ok": True,
            "accessorybillid": pk_bill,
            "upload": upload_info,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
