from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from typing import Any

# Fixed internal ERM host for this skill (not configurable).
ERM_BASE_URL = "http://10.83.2.11:8008"


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cookie", required=True, help="Raw Cookie header copied from browser")
    parser.add_argument("--timeout", type=float, default=30.0)


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


def quote_ref_name(ref_name: str, *, double: bool = False) -> str:
    once = urllib.parse.quote(ref_name, safe="")
    return urllib.parse.quote(once, safe="") if double else once


def make_client(args: argparse.Namespace) -> httpx.Client:
    import httpx

    return httpx.Client(
        headers={"Cookie": args.cookie},
        timeout=args.timeout,
        follow_redirects=True,
    )


def post_form(
    client: httpx.Client,
    *,
    base_url: str,
    path: str,
    form: dict[str, Any],
) -> dict[str, Any]:
    url = join_url(base_url, path)
    print(f"POST {url}", file=sys.stderr)
    response = client.post(
        url,
        data=form,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
    )
    print(f"STATUS {response.status_code}", file=sys.stderr)
    print(f"FINAL_URL {response.url}", file=sys.stderr)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return json.loads(response.text)


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
