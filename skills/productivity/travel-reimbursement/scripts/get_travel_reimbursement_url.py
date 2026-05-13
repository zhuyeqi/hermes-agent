from __future__ import annotations

"""Resolve the travel reimbursement add-page URL from an authenticated cookie session."""

import argparse

from erm_common import ERM_BASE_URL, add_common_args, join_url, make_client, print_json


# 差旅费报销单
TRADE_TYPE = "264X-Cxx-CLBX"
TRADE_NAME = "差旅费报销单"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Get 差旅费报销单 page URL via iwebap/menu/url (fixed ERM host)."
    )
    add_common_args(parser)
    args = parser.parse_args()

    endpoint = "iwebap/menu/url"
    payload = {"tradetype": TRADE_TYPE, "tradeName": TRADE_NAME}

    with make_client(args) as client:
        url = join_url(ERM_BASE_URL, endpoint)
        response = client.post(
            url,
            json=payload,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "*/*",
            },
        )
        response.raise_for_status()
        data = response.json()

    if not data.get("success"):
        raise RuntimeError(f"menu/url returned success=false: {data}")

    relative_url = str(data.get("url") or "")
    if not relative_url:
        raise RuntimeError(f"menu/url returned empty url: {data}")

    print_json(
        {
            "request": {"url": url, "payload": payload},
            "response": data,
            "result": {
                "relative_url": relative_url,
                "absolute_url": join_url(ERM_BASE_URL, relative_url),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())