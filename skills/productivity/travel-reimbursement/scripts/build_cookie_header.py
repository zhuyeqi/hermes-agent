from __future__ import annotations

"""Build a raw Cookie header from browser-exported cookie JSON.

Supported inputs:
- Playwright storage_state JSON: {"cookies": [...]}
- CDP Network.getAllCookies result: {"cookies": [...]} or a raw cookie list

This script cannot read HttpOnly cookies from document.cookie. The browser tool
must export the browser cookie jar through Playwright/CDP or provide a raw
Cookie request header copied from Network.
"""

import argparse
import json
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


def load_cookie_list(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        cookies = data
    elif isinstance(data, dict):
        if isinstance(data.get("cookies"), list):
            cookies = data["cookies"]
        elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("cookies"), list):
            cookies = data["data"]["cookies"]
        else:
            raise ValueError("cookie JSON must be a list or an object containing a cookies list")
    else:
        raise ValueError("cookie JSON must be a list or an object containing a cookies list")
    return [cookie for cookie in cookies if isinstance(cookie, dict)]


def build_header(cookies: list[dict[str, Any]], *, domain_filter: str = "") -> str:
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "")
        if not name:
            continue
        if domain_filter and domain_filter not in domain:
            continue
        # Replace earlier entry so the last occurrence wins (active session).
        if name in seen:
            ordered = [(n, v) for n, v in ordered if n != name]
        else:
            seen.add(name)
        ordered.append((name, value))
    return "; ".join(f"{n}={v}" for n, v in ordered)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate a raw Cookie header from browser cookie JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cookies-json", help="Playwright storage_state, CDP cookies result, or raw cookie-list JSON")
    source.add_argument("--cookie", help="Already copied raw Cookie header; validate and normalize it")
    parser.add_argument("--domain-filter", default="", help="Optional domain substring filter for cookie JSON")
    args = parser.parse_args()

    cookie_header = args.cookie or build_header(load_cookie_list(args.cookies_json), domain_filter=args.domain_filter)
    parsed = parse_cookie_header(cookie_header)
    missing = [name for name in REQUIRED_COOKIE_NAMES if not parsed.get(name)]
    print_json(
        {
            "cookie_header": cookie_header,
            "cookie_names": list(parsed),
            "has_token": bool(parsed.get("token")),
            "has_jsessionid": bool(parsed.get("JSESSIONID")),
            "missing_required_cookie_names": missing,
            "ok": not missing,
        }
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
