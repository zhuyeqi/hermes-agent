#!/usr/bin/env bash
set -euo pipefail

# Single-entry orchestrator for the travel reimbursement skill.
# ERM host: single source of truth in scripts/erm_common.py (ERM_BASE_URL).
#
# Required env:
#   SKILL_DIR         - path to this skill directory
#   ERM_ACCOUNT       - account identifier for workspace isolation
#   ITEMS_JSON        - path to items JSON (must be inside ACCOUNT_WORKSPACE)
#
# Optional env:
#   ACCOUNT_WORKSPACE - root directory for this account's workspace
#   PROFILE_DIR       - agent-browser profile dir (default: ACCOUNT_WORKSPACE/browser-profile)
#   COOKIE            - raw Cookie header; if unset, auto-exported from profile
#   ATTACHMENT_FILE   - optional single local file path to upload
#   ATTACHMENT_FILES  - optional colon-separated absolute paths for multi-file upload
#   RUN_DIR           - optional run directory (default: ACCOUNT_WORKSPACE/runs/travel-YYYYMMDD-HHMMSS)
#   DRY_RUN           - "1" to only build payload (default: 0)
#
# Output artifacts in RUN_DIR:
#   cdp_cookies.json, menu_url.json, dispatch.json, defaults.json,
#   attachment_*.json, save_form.json, save_result.json

die() {
  echo "ERROR: $*" >&2
  exit 1
}

step() {
  echo "== step: $*" >&2
}

require_env() {
  local k="$1"
  [[ -n "${!k:-}" ]] || die "missing env: $k"
}

require_env SKILL_DIR
require_env ERM_ACCOUNT
require_env ITEMS_JSON

source "${SKILL_DIR}/scripts/resolve_python_env.sh"

ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE}"
PROFILE_DIR="${PROFILE_DIR:-${ACCOUNT_WORKSPACE}/browser-profile}"
RUN_DIR="${RUN_DIR:-${ACCOUNT_WORKSPACE}/runs/travel-$(date +%Y%m%d-%H%M%S)}"

mkdir -p "$RUN_DIR"

if [[ ! -d "$SKILL_DIR/scripts" ]]; then
  die "SKILL_DIR does not look like the skill directory: $SKILL_DIR"
fi

ERM_BASE_URL="$(
  PYTHONPATH="${SKILL_DIR}/scripts" python3 -c "from erm_common import ERM_BASE_URL; print(ERM_BASE_URL)"
)"
[[ -n "$ERM_BASE_URL" ]] || die "failed to resolve ERM_BASE_URL from erm_common.py"
export ERM_BASE_URL

# Enforce ACCOUNT_WORKSPACE isolation: ITEMS_JSON and ATTACHMENT_FILES must live inside ACCOUNT_WORKSPACE.
# ITEMS_JSON and attachment paths are files: `cd file.json` fails, so resolve via dirname + basename.
canonical_abs_path() {
  local p="$1"
  if [[ -d "$p" ]]; then
    (cd "$p" && pwd -P)
    return
  fi

  local dir base
  dir="$(dirname "$p")"
  base="$(basename "$p")"
  if [[ "$dir" == "." ]]; then
    dir="$(pwd -P)"
  else
    [[ -d "$dir" ]] || die "cannot resolve path (missing directory): $p"
    dir="$(cd "$dir" && pwd -P)"
  fi
  printf '%s/%s\n' "$dir" "$base"
}

validate_workspace_path() {
  local p="$1"
  local what="$2"
  if [[ -z "$p" ]]; then return; fi
  local rp rw
  rp="$(canonical_abs_path "$p")"
  rw="$(cd "$ACCOUNT_WORKSPACE" && pwd -P)" || die "cannot resolve workspace: $ACCOUNT_WORKSPACE"
  if [[ "$rp" != "$rw"/* ]]; then
    die "$what path must be inside ACCOUNT_WORKSPACE ($ACCOUNT_WORKSPACE): $p"
  fi
}

validate_workspace_path "$ITEMS_JSON" "ITEMS_JSON"

# --- Cookie export ---
COOKIE="${COOKIE:-}"
if [[ -z "$COOKIE" ]]; then
  step "export_cookies"
  agent-browser --profile "$PROFILE_DIR" cookies get --json > "$RUN_DIR/cdp_cookies.json"

  COOKIE="$(python3 "$SKILL_DIR/scripts/build_cookie_header.py" \
    --cookies-json "$RUN_DIR/cdp_cookies.json" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['cookie_header'])")"
  [[ -n "$COOKIE" ]] || die "failed to build cookie header from profile"
fi

# --- Pipeline ---

step "get_travel_reimbursement_url"
python3 "$SKILL_DIR/scripts/get_travel_reimbursement_url.py" \
  --cookie "$COOKIE" \
  > "$RUN_DIR/menu_url.json"

python3 - <<PY
import json
from pathlib import Path

obj = json.loads(Path("$RUN_DIR/menu_url.json").read_text(encoding="utf-8"))
result = obj.get("result") or obj
u = result.get("absolute_url") or result.get("url")
if not u:
    raise SystemExit("Gate.B failed: menu_url.json must contain result.absolute_url")
print("Gate.B ok")
PY

step "capture_dispatch (network monitor)"
agent-browser --profile "$PROFILE_DIR" network requests --clear

ADD_URL="$(python3 - <<PY
import json
import os
from pathlib import Path
from urllib.parse import urljoin

base_url = os.environ["ERM_BASE_URL"]
data = json.loads(Path("$RUN_DIR/menu_url.json").read_text(encoding="utf-8"))
result = data.get("result") or data
url = result.get("absolute_url") or result.get("url")
if not url:
    raise SystemExit("menu_url.json missing result.absolute_url/url")
print(urljoin(base_url.rstrip("/") + "/", url))
PY
)"

agent-browser --profile "$PROFILE_DIR" open "$ADD_URL"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

step "extract_dispatch (request detail)"
agent-browser --profile "$PROFILE_DIR" \
  network requests --filter "/iwebap/evt/dispatch" --json > "$RUN_DIR/dispatch_requests.json"

DISPATCH_REQ_ID="$(python3 - <<PY
import json
from pathlib import Path

raw = json.loads(Path("$RUN_DIR/dispatch_requests.json").read_text(encoding="utf-8"))
if isinstance(raw, dict) and "success" in raw:
    raw = raw.get("data", raw)
entries = raw if isinstance(raw, list) else raw.get("requests", raw.get("entries", []))
matches = [e for e in entries if "/iwebap/evt/dispatch" in (e.get("url") or "")]
if not matches:
    raise SystemExit(f"Gate.C failed: no /iwebap/evt/dispatch request (total: {len(entries)})")
req_id = matches[-1].get("requestId") or matches[-1].get("id") or ""
if not req_id:
    raise SystemExit("Gate.C failed: dispatch request missing requestId")
print(req_id)
PY
)"

agent-browser --profile "$PROFILE_DIR" \
  network request "$DISPATCH_REQ_ID" --json > "$RUN_DIR/dispatch_detail.json"

python3 - <<PY
import json
from pathlib import Path

raw = json.loads(Path("$RUN_DIR/dispatch_detail.json").read_text(encoding="utf-8"))
if isinstance(raw, dict) and "success" in raw:
    raw = raw.get("data", raw)
body = raw.get("responseBody") or raw.get("content", {}).get("text", "")
if not body:
    raise SystemExit("Gate.C failed: dispatch response has empty body")

data = json.loads(body)
if not isinstance(data, dict) or "dataTables" not in data:
    raise SystemExit("Gate.C failed: dispatch body missing dataTables")

Path("$RUN_DIR/dispatch.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print("Gate.C ok")
PY

step "extract_dispatch_defaults"
python3 "$SKILL_DIR/scripts/extract_dispatch_defaults.py" \
  --dispatch-json "$RUN_DIR/dispatch.json" \
  > "$RUN_DIR/defaults.json"

# Gate.D: verify essential defaults exist (head and at least one body table has fields)
python3 - <<PY
import json
from pathlib import Path

d = json.loads(Path("$RUN_DIR/defaults.json").read_text(encoding="utf-8"))
if "defaults" in d:
    d = d["defaults"]
head = d.get("head") or {}
transport = d.get("transport") or {}
hotel = d.get("hotel") or {}
subsidy = d.get("subsidy") or {}

missing = []
for k in ("pk_org_v", "deptid_v", "jsfs", "skyhzh"):
    if not head.get(k):
        missing.append(f"head.{k}")
if not (transport or hotel or subsidy):
    missing.append("at least one of transport/hotel/subsidy defaults")
if missing:
    raise SystemExit("Gate.D failed: missing " + ", ".join(missing))
print("Gate.D ok")
PY

# Attachment upload (validate paths inside ACCOUNT_WORKSPACE)
accessorybillid=""
attachment_files=()
ATTACHMENT_FILE="${ATTACHMENT_FILE:-}"
ATTACHMENT_FILES="${ATTACHMENT_FILES:-}"
if [[ -n "$ATTACHMENT_FILES" ]]; then
  IFS=':' read -r -a attachment_files <<< "$ATTACHMENT_FILES"
elif [[ -n "$ATTACHMENT_FILE" ]]; then
  attachment_files=("$ATTACHMENT_FILE")
fi

for f in "${attachment_files[@]:-}"; do
  validate_workspace_path "$f" "ATTACHMENT_FILE"
done

if (( ${#attachment_files[@]} > 0 )); then
  total=${#attachment_files[@]}
  for idx in "${!attachment_files[@]}"; do
    f="${attachment_files[$idx]}"
    [[ -f "$f" ]] || die "attachment not found: $f"
    step "upload_attachment[$((idx+1))/$total] $f"

    upload_args=( --cookie "$COOKIE" --file "$f" --billtype "264X-Cxx-CLBX" )
    [[ -n "$accessorybillid" ]] && upload_args+=( --pk-bill "$accessorybillid" )

    out_json="$RUN_DIR/attachment_$((idx+1)).json"
    python3 "$SKILL_DIR/scripts/upload_reimbursement_attachment.py" \
      "${upload_args[@]}" > "$out_json"

    bid="$(OUT_JSON="$out_json" python3 - <<'PY'
import json, os, sys
obj = json.loads(open(os.environ["OUT_JSON"]).read())
if not obj.get("ok"):
    sys.exit("Gate.E failed: upload not ok")
bid = obj.get("accessorybillid") or ""
if not bid:
    sys.exit("Gate.E failed: missing accessorybillid")
print(bid)
PY
)"

    if [[ -z "$accessorybillid" ]]; then
      accessorybillid="$bid"
      cp "$out_json" "$RUN_DIR/attachment.json"
    elif [[ "$bid" != "$accessorybillid" ]]; then
      die "Gate.E failed: accessorybillid drift ($bid vs $accessorybillid)"
    fi
  done
  step "attachment_ok accessorybillid=$accessorybillid files=$total"
fi

# Save step: invoke save script with items-json
step "save_bill"
python3 "$SKILL_DIR/scripts/save_travel_reimbursement_from_dispatch.py" \
  --cookie "$COOKIE" \
  --dispatch-json "$RUN_DIR/dispatch.json" \
  --items-json "$ITEMS_JSON" \
  --accessorybillid "$accessorybillid" \
  --save-form-out "$RUN_DIR/save_form.json" \
  ${DRY_RUN:+--dry-run} \
  > "$RUN_DIR/save_result.json"

python3 - <<PY
import json
from pathlib import Path

out = json.loads(Path("$RUN_DIR/save_result.json").read_text(encoding="utf-8"))
if not out.get("ok"):
    raise SystemExit(f"save_bill failed: {out}")
print("save_bill ok")
PY

step "done"
echo "Artifacts in: $RUN_DIR" >&2
