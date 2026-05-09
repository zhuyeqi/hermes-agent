#!/usr/bin/env bash
set -euo pipefail

# Single-entry orchestrator for the reimbursement skill.
# Intentionally strict: stops on missing artifacts and prints evidence.
#
# Required env:
#   SKILL_DIR  - path to this skill directory
#   BASE_URL   - ERM base URL, e.g. http://10.83.2.11:8008
#   COOKIE     - raw Cookie request header value (single line, no "Cookie:" prefix)
#
# Optional env:
#   CDP_PORT        - default: 9222
#   ATTACHMENT_FILE - optional local file path to upload
#   DRY_RUN         - "1" to only build payload (default: 0)
#
# Required args:
#   --zy --amount --tax-amount --vat-amount --expense-item --invoice-type --invoice-no
#
# Output artifacts in current working directory:
#   menu_url.json, dispatch.json, defaults.json, attachment.json (optional), save_result.json

CDP_PORT="${CDP_PORT:-9222}"
ATTACHMENT_FILE="${ATTACHMENT_FILE:-}"
DRY_RUN="${DRY_RUN:-0}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

step() {
  echo "== step: $*" >&2
}

evidence_dispatch_failure() {
  echo "== evidence: current_url" >&2
  agent-browser --cdp "$CDP_PORT" get url || true
  echo "== evidence: tabs" >&2
  agent-browser --cdp "$CDP_PORT" --json tab list || true
  echo "== evidence: dispatch_requests" >&2
  agent-browser --cdp "$CDP_PORT" --json network requests --filter "/iwebap/evt/dispatch" || true
}

require_env() {
  local k="$1"
  [[ -n "${!k:-}" ]] || die "missing env: $k"
}

require_env SKILL_DIR
require_env BASE_URL
require_env COOKIE

if [[ ! -d "$SKILL_DIR/scripts" ]]; then
  die "SKILL_DIR does not look like the skill directory: $SKILL_DIR"
fi

step "get_general_reimbursement_url"
python3 "$SKILL_DIR/scripts/get_general_reimbursement_url.py" \
  --base-url "$BASE_URL" \
  --cookie "$COOKIE" \
  > menu_url.json

python3 - <<'PY'
import json
from pathlib import Path

obj = json.loads(Path("menu_url.json").read_text(encoding="utf-8"))
result = obj.get("result") or {}
u = result.get("absolute_url")
if not u:
    raise SystemExit("Gate.B failed: menu_url.json must contain result.absolute_url")
print("Gate.B ok")
PY

step "capture_dispatch (agent-browser network log + new tab)"
agent-browser --cdp "$CDP_PORT" network requests --clear

ADD_URL="$(python3 - <<'PY'
import json, os
from pathlib import Path
from urllib.parse import urljoin

base_url = os.environ["BASE_URL"]
data = json.loads(Path("menu_url.json").read_text(encoding="utf-8"))
result = data.get("result") or data
url = result.get("absolute_url") or result.get("url")
if not url:
    raise SystemExit("menu_url.json missing result.absolute_url/url")
print(urljoin(base_url.rstrip("/") + "/", url))
PY
)"

agent-browser --cdp "$CDP_PORT" --json tab list > /tmp/erm_tabs_before.json
agent-browser --cdp "$CDP_PORT" open "$ADD_URL"
agent-browser --cdp "$CDP_PORT" wait 5000
agent-browser --cdp "$CDP_PORT" --json tab list > /tmp/erm_tabs_after.json

python3 - <<'PY'
import json
from pathlib import Path

before = json.loads(Path("/tmp/erm_tabs_before.json").read_text(encoding="utf-8"))
after = json.loads(Path("/tmp/erm_tabs_after.json").read_text(encoding="utf-8"))

def extract_tabs(x):
    if isinstance(x, dict):
        if isinstance(x.get("tabs"), list):
            return x["tabs"]
        data = x.get("data")
        if isinstance(data, dict) and isinstance(data.get("tabs"), list):
            return data["tabs"]
    if isinstance(x, list):
        return x
    return []

tabs_before = extract_tabs(before)
tabs_after = extract_tabs(after)

def tab_key(t):
    if not isinstance(t, dict):
        return None
    return (t.get("id") or t.get("index") or t.get("n"), t.get("url") or t.get("title"))

keys_before = set(k for k in (tab_key(t) for t in tabs_before) if k)
new_tabs = [t for t in tabs_after if tab_key(t) and tab_key(t) not in keys_before]

def tab_index(t):
    if not isinstance(t, dict):
        return None
    return t.get("id") or t.get("index") or t.get("n")

chosen = new_tabs[-1] if new_tabs else (tabs_after[-1] if tabs_after else None)
idx = tab_index(chosen)
if idx is None:
    raise SystemExit("cannot determine tab index; switch manually and rerun")
Path("/tmp/erm_tab_to_use.txt").write_text(str(idx), encoding="utf-8")
print(idx)
PY

TAB_TO_USE="$(python3 -c 'from pathlib import Path; print(Path("/tmp/erm_tab_to_use.txt").read_text().strip())')"
agent-browser --cdp "$CDP_PORT" tab "$TAB_TO_USE"
agent-browser --cdp "$CDP_PORT" wait 2000

agent-browser --cdp "$CDP_PORT" --json network requests --filter "/iwebap/evt/dispatch" > /tmp/dispatch_requests.json

python3 - <<'PY'
import json
from pathlib import Path

raw = json.loads(Path("/tmp/dispatch_requests.json").read_text(encoding="utf-8"))
requests = ((raw.get("data") or {}).get("requests") or raw.get("requests") or [])

def values(node):
    if isinstance(node, dict):
        for v in node.values():
            yield v
            yield from values(v)
    elif isinstance(node, list):
        for v in node:
            yield v
            yield from values(v)

payload = None
hit_url = None

for req in reversed(requests):
    url = str(req.get("url") or req.get("request", {}).get("url") or req.get("response", {}).get("url") or "")
    if "/iwebap/evt/dispatch" not in url:
        continue
    for v in values(req):
        if not isinstance(v, str) or "dataTables" not in v:
            continue
        try:
            obj = json.loads(v)
        except Exception:
            continue
        if isinstance(obj, dict) and "dataTables" in obj:
            payload = obj
            hit_url = url
            break
    if payload is not None:
        break

if payload is None:
    raise SystemExit("Gate.C failed: dispatch response body not found in agent-browser network log")

Path("dispatch.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print("Gate.C ok")
print(f"dispatch_url={hit_url}")
PY

step "extract_dispatch_defaults"
python3 "$SKILL_DIR/scripts/extract_dispatch_defaults.py" \
  --dispatch-json dispatch.json \
  > defaults.json

python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("defaults.json").read_text(encoding="utf-8"))
head = d.get("head") or {}
body = d.get("body") or {}
missing = []
for k in ("pk_org_v", "deptid_v", "jsfs", "skyhzh"):
    if not head.get(k):
        missing.append(f"head.{k}")
if not body.get("defitem13"):
    missing.append("body.defitem13")
if missing:
    raise SystemExit("Gate.D failed: missing " + ", ".join(missing))
print("Gate.D ok")
PY

accessorybillid=""
if [[ -n "$ATTACHMENT_FILE" ]]; then
  step "upload_attachment"
  python3 "$SKILL_DIR/scripts/upload_reimbursement_attachment.py" \
    --base-url "$BASE_URL" \
    --cookie "$COOKIE" \
    --file "$ATTACHMENT_FILE" \
    > attachment.json

  accessorybillid="$(python3 - <<'PY'
import json
from pathlib import Path
obj = json.loads(Path("attachment.json").read_text(encoding="utf-8"))
if not obj.get("ok"):
    raise SystemExit("Gate.E failed: upload not ok")
bid = obj.get("accessorybillid") or ""
if not bid:
    raise SystemExit("Gate.E failed: missing accessorybillid")
print(bid)
PY
)"
  step "attachment_ok accessorybillid=$accessorybillid"
fi

step "save_bill"
save_args=(
  --base-url "$BASE_URL"
  --cookie "$COOKIE"
  --dispatch-json dispatch.json
  --accessorybillid "$accessorybillid"
)

python3 "$SKILL_DIR/scripts/save_general_reimbursement_from_dispatch.py" \
  "${save_args[@]}" \
  "$@" \
  --dry-run > /tmp/save_dry_run.json

if [[ "$DRY_RUN" == "1" ]]; then
  cp /tmp/save_dry_run.json save_result.json
  step "dry_run_only done"
  exit 0
fi

python3 "$SKILL_DIR/scripts/save_general_reimbursement_from_dispatch.py" \
  "${save_args[@]}" \
  "$@" \
  > save_result.json

step "done (artifacts: menu_url.json dispatch.json defaults.json save_result.json)"

