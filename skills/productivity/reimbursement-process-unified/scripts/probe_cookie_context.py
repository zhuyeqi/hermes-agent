from __future__ import annotations

"""Inspect whether a browser Cookie header is enough to call ERM APIs.

Run this after browser login. By default it only decodes the Cookie header.
Use --probe-msgtype-list to verify the Cookie against /mp/msgtype/list.
"""

import argparse
import time

from erm_common import ERM_BASE_URL, add_common_args, join_url, make_client, parse_cookie_header, print_json


REQUIRED_COOKIE_NAMES = (
    "JSESSIONID",
    "token",
    "user_org",
    "pk_unit",
    "datasource",
    "userid",
    "usercode",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect cookie-derived ERM context.")
    add_common_args(parser)
    parser.add_argument(
        "--probe-msgtype-list",
        action="store_true",
        help="GET /mp/msgtype/list to verify the Cookie works in the current session.",
    )
    args = parser.parse_args()

    cookie = parse_cookie_header(args.cookie)
    missing = [name for name in REQUIRED_COOKIE_NAMES if not cookie.get(name)]
    out = {
        "base_url_normalized": ERM_BASE_URL.rstrip("/"),
        "cookie_context": {
            "user_org(pk_org_candidate)": cookie.get("user_org"),
            "pk_unit(pk_group_candidate)": cookie.get("pk_unit"),
            "pk_group": cookie.get("pk_group"),
            "userid": cookie.get("userid"),
            "usercode": cookie.get("usercode"),
            "datasource": cookie.get("datasource"),
            "language": cookie.get("LA_K1"),
        },
        "has_token": bool(cookie.get("token")),
        "has_jsessionid": bool(cookie.get("JSESSIONID")),
        "missing_required_cookie_names": missing,
    }

    if args.probe_msgtype_list:
        with make_client(args) as client:
            response = client.get(
                join_url(ERM_BASE_URL, f"mp/msgtype/list?_={int(time.time() * 1000)}"),
                headers={"Accept": "application/json, text/plain, */*"},
            )
        out["msgtype_list_probe"] = {
            "status_code": response.status_code,
            "final_url": str(response.url),
            "content_type": response.headers.get("content-type", ""),
            "looks_authenticated": (
                response.status_code == 200
                and "application/json" in response.headers.get("content-type", "")
                and "TASK" in response.text
            ),
        }

    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
