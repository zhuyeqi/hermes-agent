from __future__ import annotations

"""Merge login response Set-Cookie headers into a raw Cookie request header.

Use this when agentbrowser can capture the automatic POST /portal/core response
after login. Pass the response Set-Cookie header(s) and, if available, an
existing request Cookie header from before login.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from erm_common import parse_cookie_header, print_json


REQUIRED_COOKIE_NAMES = (
    "JSESSIONID",
    "token",
    "user_org",
    "pk_unit",
    "datasource",
    "userid",
    "usercode",
)

COOKIE_SPLIT_RE = re.compile(r",\s*(?=[A-Za-z_][A-Za-z0-9_]*=)")


def split_set_cookie(header: str) -> list[str]:
    return [part.strip() for part in COOKIE_SPLIT_RE.split(header) if part.strip()]


def parse_set_cookie(headers: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for header in headers:
        for item in split_set_cookie(header):
            pair = item.split(";", 1)[0].strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            name = name.strip()
            if not name:
                continue
            out[name] = value.strip()
    return out


def read_headers_json(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(item) for item in data]
    if isinstance(data, dict):
        values: list[str] = []
        for key, value in data.items():
            if key.lower() != "set-cookie":
                continue
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))
        return values
    raise ValueError("--headers-json must contain a headers object or Set-Cookie list")


def build_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge Set-Cookie headers into a Cookie request header.")
    parser.add_argument("--base-cookie", default="", help="Existing raw Cookie header, if available")
    parser.add_argument("--set-cookie", action="append", default=[], help="Set-Cookie header value; may repeat")
    parser.add_argument("--headers-json", default="", help="JSON object/list exported from captured response headers")
    args = parser.parse_args()

    set_cookie_headers = list(args.set_cookie)
    if args.headers_json:
        set_cookie_headers.extend(read_headers_json(args.headers_json))
    if not set_cookie_headers:
        raise SystemExit("pass --set-cookie or --headers-json from the /portal/core response")

    merged = parse_cookie_header(args.base_cookie)
    merged.update(parse_set_cookie(set_cookie_headers))
    missing = [name for name in REQUIRED_COOKIE_NAMES if not merged.get(name)]
    print_json(
        {
            "cookie_header": build_cookie_header(merged),
            "cookie_names": list(merged),
            "has_token": bool(merged.get("token")),
            "has_jsessionid": bool(merged.get("JSESSIONID")),
            "missing_required_cookie_names": missing,
            "ok": not missing,
        }
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
