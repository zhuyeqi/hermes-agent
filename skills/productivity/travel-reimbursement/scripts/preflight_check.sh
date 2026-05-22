#!/usr/bin/env bash
set -euo pipefail

# Pre-flight validation for travel reimbursement skill.
# Checks all input data before any network or browser activity.
# Exit 0 = all checks pass (Phase 5 may warn); Exit 1 = errors reported to stderr.

errors=()

# --- Phase 1: Dependencies ---
for cmd in python3 agent-browser; do
  if ! command -v "$cmd" &>/dev/null; then
    errors+=("[FAIL] Phase 1: dependency not found: $cmd")
  fi
done

# --- Phase 2: Required environment variables ---
for var in SKILL_DIR ERM_ACCOUNT ITEMS_JSON; do
  if [[ -z "${!var:-}" ]]; then
    errors+=("[FAIL] Phase 2: $var is not set")
  fi
done

# Resolve Python env + workspace paths (same as run_reimbursement_pipeline.sh / login_erm.sh)
if [[ -n "${SKILL_DIR:-}" ]] && [[ -f "${SKILL_DIR}/scripts/lib/init.sh" ]]; then
  # shellcheck source=lib/init.sh
  source "${SKILL_DIR}/scripts/lib/init.sh"
  # shellcheck source=lib/resolve_python_env.sh
  source "${ERM_SCRIPT_LIB}/resolve_python_env.sh"
fi
if [[ -n "${SKILL_DIR:-}" ]] && [[ -f "${SKILL_DIR}/scripts/lib/erm_workspace.sh" ]]; then
  # shellcheck source=lib/erm_workspace.sh
  source "${SKILL_DIR}/scripts/lib/erm_workspace.sh"
  if [[ -n "${ERM_ACCOUNT:-}" ]]; then
    if [[ "$ERM_ACCOUNT" == */* || "$ERM_ACCOUNT" == *..* ]]; then
      errors+=("[FAIL] Phase 2: ERM_ACCOUNT must be a plain account id (no / or ..)")
    else
      erm_resolve_workspace
    fi
  fi
fi

# --- Phase 1c: Browser daemon health (after workspace resolved) ---
if command -v agent-browser &>/dev/null && [[ -n "${SKILL_DIR:-}" ]] && [[ -n "${PROFILE_DIR:-}" ]]; then
  if ! SKILL_DIR="$SKILL_DIR" PROFILE_DIR="$PROFILE_DIR" bash "${SKILL_DIR}/scripts/check_browser_health.sh" >/dev/null 2>"${TMPDIR:-/tmp}/erm-preflight-browser.$$.json"; then
    _bh_msg="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("message","browser health check failed"))' "${TMPDIR:-/tmp}/erm-preflight-browser.$$.json" 2>/dev/null || echo "browser health check failed")"
    errors+=("[FAIL] Phase 1c: $_bh_msg (see stderr JSON from check_browser_health.sh)")
    cat "${TMPDIR:-/tmp}/erm-preflight-browser.$$.json" >&2 2>/dev/null || true
    rm -f "${TMPDIR:-/tmp}/erm-preflight-browser.$$.json"
  else
    rm -f "${TMPDIR:-/tmp}/erm-preflight-browser.$$.json"
  fi
fi

# Phase 1b: httpx import check (after resolve_python_env.sh so correct python3 is on PATH)
if command -v python3 &>/dev/null && ! python3 -c "import httpx" 2>/dev/null; then
  errors+=("[FAIL] Phase 1: python3 found but httpx module not available")
fi

# Helper: resolve to canonical absolute path (same logic as run_reimbursement_pipeline.sh)
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
  elif [[ -d "$dir" ]]; then
    dir="$(cd "$dir" && pwd -P)"
  else
    echo "$p"
    return
  fi
  printf '%s/%s\n' "$dir" "$base"
}

# --- Phase 3: Path isolation (ITEMS_JSON and attachments under ACCOUNT_WORKSPACE) ---
if [[ -n "${ITEMS_JSON:-}" ]]; then
  if [[ -z "${ACCOUNT_WORKSPACE:-}" ]]; then
    errors+=("[FAIL] Phase 3: ERM_ACCOUNT must be set to resolve workspace for ITEMS_JSON")
  elif [[ ! -d "$ACCOUNT_WORKSPACE" ]]; then
    errors+=("[FAIL] Phase 3: workspace is not a directory ($ACCOUNT_WORKSPACE); create it (mkdir -p \"\$PWD/\${ERM_ACCOUNT}/items\") — see SKILL.md step 0)")
  fi
fi

if [[ -n "${ATTACHMENT_FILE:-}${ATTACHMENT_FILES:-}" ]]; then
  if [[ -z "${ACCOUNT_WORKSPACE:-}" ]]; then
    errors+=("[FAIL] Phase 3: ERM_ACCOUNT must be set to resolve workspace for attachments")
  elif [[ ! -d "$ACCOUNT_WORKSPACE" ]]; then
    errors+=("[FAIL] Phase 3: workspace is not a directory ($ACCOUNT_WORKSPACE); create attachments dir — see SKILL.md step 0)")
  fi
fi

if [[ -n "${ACCOUNT_WORKSPACE:-}" ]] && [[ -d "${ACCOUNT_WORKSPACE:-}" ]]; then
  aw_real="$(cd "${ACCOUNT_WORKSPACE}" && pwd -P)"

  if [[ -n "${ITEMS_JSON:-}" ]]; then
    items_real="$(canonical_abs_path "$ITEMS_JSON")"
    if [[ "$items_real" != "$aw_real"/* ]]; then
      errors+=("[FAIL] Phase 3: ITEMS_JSON ($ITEMS_JSON) is outside ACCOUNT_WORKSPACE ($ACCOUNT_WORKSPACE)")
    fi
  fi

  if [[ -n "${ATTACHMENT_FILE:-}" ]]; then
    att_real="$(canonical_abs_path "$ATTACHMENT_FILE")"
    if [[ "$att_real" != "$aw_real"/* ]]; then
      errors+=("[FAIL] Phase 3: ATTACHMENT_FILE ($ATTACHMENT_FILE) is outside ACCOUNT_WORKSPACE ($ACCOUNT_WORKSPACE)")
    fi
  fi

  if [[ -n "${ATTACHMENT_FILES:-}" ]]; then
    IFS=':' read -ra _att_files <<< "$ATTACHMENT_FILES"
    for f in "${_att_files[@]}"; do
      f_real="$(canonical_abs_path "$f")"
      if [[ "$f_real" != "$aw_real"/* ]]; then
        errors+=("[FAIL] Phase 3: attachment ($f) is outside ACCOUNT_WORKSPACE ($ACCOUNT_WORKSPACE)")
      fi
    done
  fi
fi

# --- Phase 4: ITEMS_JSON validation ---
if [[ -n "${ITEMS_JSON:-}" ]]; then
  if [[ ! -f "$ITEMS_JSON" ]]; then
    errors+=("[FAIL] Phase 4: ITEMS_JSON file not found: $ITEMS_JSON")
  else
    _py4_out=$(python3 - "$ITEMS_JSON" 2>&1 <<'PYEOF'
import json, sys

path = sys.argv[1]
errs = []

try:
    with open(path) as f:
        data = json.load(f)
except json.JSONDecodeError:
    print(f"[FAIL] Phase 4: {path} is not valid JSON", file=sys.stderr)
    sys.exit(0)
except OSError as e:
    print(f"[FAIL] Phase 4: {path}: {e}", file=sys.stderr)
    sys.exit(0)

if not data.get("summary"):
    errs.append(f"[FAIL] Phase 4: {path}: missing required field: summary")

categories = ["transports", "hotels", "subsidies"]
has_data = any(isinstance(data.get(c), list) and len(data[c]) > 0 for c in categories)
if not has_data:
    errs.append(f"[FAIL] Phase 4: {path}: must contain at least one of transports/hotels/subsidies")

required = {
    "transports": ["departure_date", "arrival_date", "vehicle", "invoice_form", "invoice_no", "amount"],
    "hotels": ["city_type", "days", "invoice_type", "invoice_no", "amount"],
    "subsidies": ["days", "tool", "official_car_pickup", "hosted_by_counterparty"],
}

for cat, fields in required.items():
    items = data.get(cat, [])
    if not isinstance(items, list):
        continue
    for i, item in enumerate(items):
        for field in fields:
            val = item.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errs.append(f"[FAIL] Phase 4: {path}: {cat}[{i}] missing required field: {field}")

for e in errs:
    print(e, file=sys.stderr)
PYEOF
)
    if [[ -n "$_py4_out" ]]; then
      while IFS= read -r _line || [[ -n "${_line:-}" ]]; do
        [[ -n "${_line:-}" ]] && errors+=("$_line")
      done <<< "$_py4_out"
    fi
  fi
fi

# --- Phase 4b: Enum validation ---
if [[ -n "${ITEMS_JSON:-}" ]] && [[ -f "${ITEMS_JSON:-}" ]] && [[ -n "${SKILL_DIR:-}" ]]; then
  if ! python3 "${SKILL_DIR}/scripts/validate_travel_items_enums.py" \
    --items-json "$ITEMS_JSON" 2>"${TMPDIR:-/tmp}/erm-preflight-enums.$$.json"; then
    errors+=("[FAIL] Phase 4b: items enum validation failed")
    cat "${TMPDIR:-/tmp}/erm-preflight-enums.$$.json" >&2 2>/dev/null || true
    rm -f "${TMPDIR:-/tmp}/erm-preflight-enums.$$.json"
  else
    rm -f "${TMPDIR:-/tmp}/erm-preflight-enums.$$.json"
  fi
fi

# --- Phase 5: Attachment file existence ---
_has_invoices=false
if [[ -n "${ITEMS_JSON:-}" ]] && [[ -f "${ITEMS_JSON:-}" ]]; then
  _invoice_count=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
n=sum(len(d.get(c,[])) for c in('transports','hotels'))
print(n)
" "$ITEMS_JSON" 2>/dev/null || echo 0)
  if [[ "$_invoice_count" -gt 0 ]]; then _has_invoices=true; fi
fi

if [[ "$_has_invoices" == true ]]; then
  if [[ -n "${ATTACHMENT_FILES:-}" ]]; then
    IFS=':' read -ra _att_files <<< "$ATTACHMENT_FILES"
    for f in "${_att_files[@]}"; do
      if [[ ! -f "$f" ]]; then
        errors+=("[FAIL] Phase 5: attachment not found: $f")
      fi
    done
  elif [[ -n "${ATTACHMENT_FILE:-}" ]]; then
    if [[ ! -f "$ATTACHMENT_FILE" ]]; then
      errors+=("[FAIL] Phase 5: attachment not found: $ATTACHMENT_FILE")
    fi
  else
    errors+=("[FAIL] Phase 5: ITEMS_JSON has transport/hotel entries but neither ATTACHMENT_FILE nor ATTACHMENT_FILES is set")
  fi
elif [[ -n "${ATTACHMENT_FILES:-}" ]]; then
  IFS=':' read -ra _att_files <<< "$ATTACHMENT_FILES"
  for f in "${_att_files[@]}"; do
    if [[ ! -f "$f" ]]; then
      errors+=("[FAIL] Phase 5: attachment not found: $f")
    fi
  done
elif [[ -n "${ATTACHMENT_FILE:-}" ]]; then
  if [[ ! -f "$ATTACHMENT_FILE" ]]; then
    errors+=("[FAIL] Phase 5: attachment not found: $ATTACHMENT_FILE")
  fi
fi

# --- Report ---
if [[ ${#errors[@]} -gt 0 ]]; then
  printf '%s\n' "${errors[@]}" >&2
  exit 1
fi
exit 0
