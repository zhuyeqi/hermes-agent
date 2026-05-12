from __future__ import annotations

"""Resolve the general reimbursement add-page URL from an authenticated cookie session."""

import argparse

from erm_common import add_common_args, join_url, make_client, print_json


TRADE_TYPE = "264X-Cxx-TYBXD"
TRADE_NAME = "通用报销单"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Get 通用报销单 page URL via iwebap/menu/url; --base-url defaults to the verified ERM host."
        )
    )
    add_common_args(parser)
    args = parser.parse_args()

    endpoint = "iwebap/menu/url"
    payload = {"tradetype": TRADE_TYPE, "tradeName": TRADE_NAME}

    with make_client(args) as client:
        url = join_url(args.base_url, endpoint)
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
                "absolute_url": join_url(args.base_url, relative_url),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
