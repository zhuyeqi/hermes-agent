# NON-RUNTIME — maintainer debug only. See archive/README.md.
from __future__ import annotations

"""Post a prebuilt ERM savebill form.

This is mainly a fallback/debug tool. Prefer save_general_reimbursement_from_dispatch.py
for normal runs because it builds the form from dispatch defaults and user data.
"""

import argparse
import json
import sys

from erm_common import ERM_BASE_URL, add_common_args, make_client, post_form, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 04: post an already-built savebill form JSON.")
    add_common_args(parser)
    parser.add_argument(
        "--form-json",
        required=True,
        help="Path to JSON file containing the save_form object printed by 03_build_payload.py",
    )
    args = parser.parse_args()

    with open(args.form_json, encoding="utf-8") as f:
        data = json.load(f)
    form = data.get("save_form") if isinstance(data, dict) and "save_form" in data else data
    if not isinstance(form, dict):
        print("form json must be an object or contain save_form object", file=sys.stderr)
        return 2

    with make_client(args) as client:
        out = post_form(
            client,
            base_url=ERM_BASE_URL,
            path="/iwebap/jkbx_maintain_ctr/savebill",
            form=form,
        )

    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
