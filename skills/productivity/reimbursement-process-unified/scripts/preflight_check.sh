#!/usr/bin/env bash
set -euo pipefail

# Pre-flight validation for unified reimbursement skill.
# Checks all input data before any network or browser activity.
# Exit 0 = checks pass (Phase 5 may print a warning to stderr). Exit 1 = errors on stderr.

errors=()

# --- Phase 1: Dependencies ---
for cmd in python3 agent-browser; do
  if ! command -v "$cmd" &>/dev/null; then
    errors+=("[FAIL] Phase 1: dependency not found: $cmd")
  fi
done

# --- Phase 2: Required environment variables ---
for var in SKILL_DIR ERM_ACCOUNT INVOICES_JSON; do
  if [[ -z "${!var:-}" ]]; then
    errors+=("[FAIL] Phase 2: $var is not set")
  fi
done

# Resolve Python env (same as run_reimbursement_pipeline.sh / login_erm.sh)
if [[ -n "${SKILL_DIR:-}" ]] && [[ -f "${SKILL_DIR}/scripts/resolve_python_env.sh" ]]; then
  source "${SKILL_DIR}/scripts/resolve_python_env.sh"
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

# --- Phase 3: Path isolation ---
ACCOUNT_WORKSPACE="${ACCOUNT_WORKSPACE:-$PWD/${ERM_ACCOUNT:-}}"

if [[ -n "${ATTACHMENT_FILE:-}${ATTACHMENT_FILES:-}" ]]; then
  if [[ ! -d "$ACCOUNT_WORKSPACE" ]]; then
    errors+=("[FAIL] Phase 3: ACCOUNT_WORKSPACE is not a directory ($ACCOUNT_WORKSPACE); create it (mkdir -p) before using attachments — see SKILL.md step 0)")
  fi
fi

if [[ -n "$ACCOUNT_WORKSPACE" ]] && [[ -d "$ACCOUNT_WORKSPACE" ]]; then
  aw_real="$(cd "$ACCOUNT_WORKSPACE" && pwd -P)"

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

# --- Phase 4: INVOICES_JSON validation (path required in Phase 2)
if [[ -n "${INVOICES_JSON:-}" ]]; then
  if [[ ! -f "$INVOICES_JSON" ]]; then
    errors+=("[FAIL] Phase 4: INVOICES_JSON file not found: $INVOICES_JSON")
  else
    _py4_out=$(python3 - "$INVOICES_JSON" 2>&1 <<'PYEOF'
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

if not isinstance(data, list):
    print(f"[FAIL] Phase 4: {path}: must be a JSON array, got {type(data).__name__}", file=sys.stderr)
    sys.exit(0)

if len(data) == 0:
    print(f"[FAIL] Phase 4: {path}: array must contain at least 1 entry", file=sys.stderr)
    sys.exit(0)

required_fields = ("amount", "tax_amount", "vat_amount", "invoice_no", "expense_item", "invoice_type")

for i, entry in enumerate(data):
    for field in required_fields:
        val = entry.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errs.append(f"[FAIL] Phase 4: {path}: entry[{i}] missing or empty field: {field}")

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

# --- Phase 5: Attachment file existence ---
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
  if [[ -n "${INVOICES_JSON:-}" ]] && [[ -f "${INVOICES_JSON:-}" ]]; then
    echo "[WARN] Phase 5: INVOICES_JSON present but no ATTACHMENT_FILE/ATTACHMENT_FILES set (attachments are optional for general reimbursement)" >&2
  fi
fi

# --- Report ---
if [[ ${#errors[@]} -gt 0 ]]; then
  printf '%s\n' "${errors[@]}" >&2
  exit 1
fi
exit 0
