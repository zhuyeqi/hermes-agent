#!/usr/bin/env bash
set -euo pipefail

# Pre-flight validation for travel reimbursement skill.
# Checks all input data before any network or browser activity.
# Exit 0 = all checks pass (silent); Exit 1 = errors reported to stderr.

errors=()

# --- Phase 1: Dependencies ---
for cmd in python3 jq agent-browser; do
  if ! command -v "$cmd" &>/dev/null; then
    errors+=("[FAIL] Phase 1: dependency not found: $cmd")
  fi
done

# --- Phase 2: Environment variables ---
for var in SKILL_DIR ERM_ACCOUNT ACCOUNT_WORKSPACE ITEMS_JSON; do
  if [[ -z "${!var:-}" ]]; then
    errors+=("[FAIL] Phase 2: $var is not set")
  fi
done

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
if [[ -n "${ACCOUNT_WORKSPACE:-}" ]] && [[ -d "${ACCOUNT_WORKSPACE:-}" ]]; then
  aw_real="$(cd "${ACCOUNT_WORKSPACE}" && pwd -P)"

  if [[ -n "${ITEMS_JSON:-}" ]]; then
    items_real="$(canonical_abs_path "$ITEMS_JSON")"
    if [[ "$items_real" != "$aw_real"/* ]]; then
      errors+=("[FAIL] Phase 3: ITEMS_JSON ($ITEMS_JSON) is outside ACCOUNT_WORKSPACE ($ACCOUNT_WORKSPACE)")
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
  elif ! jq '.' "$ITEMS_JSON" &>/dev/null; then
    errors+=("[FAIL] Phase 4: $ITEMS_JSON is not valid JSON")
  else
    # summary
    if [[ -z "$(jq -r '.summary // empty' "$ITEMS_JSON")" ]]; then
      errors+=("[FAIL] Phase 4: $ITEMS_JSON: missing required field: summary")
    fi

    # at least one category with entries
    _has_data=false
    for _cat in transports hotels subsidies; do
      _len=$(jq ".$_cat | length" "$ITEMS_JSON" 2>/dev/null || echo 0)
      if [[ "$_len" -gt 0 ]]; then _has_data=true; break; fi
    done
    if [[ "$_has_data" == false ]]; then
      errors+=("[FAIL] Phase 4: $ITEMS_JSON: must contain at least one of transports/hotels/subsidies")
    fi

    # transports[] required fields
    _tc=$(jq '.transports | length' "$ITEMS_JSON" 2>/dev/null || echo 0)
    for ((_i=0; _i<_tc; _i++)); do
      for _f in departure_date arrival_date vehicle invoice_form invoice_no amount; do
        _v=$(jq -r ".transports[$_i].$_f // empty" "$ITEMS_JSON")
        if [[ -z "$_v" ]]; then
          errors+=("[FAIL] Phase 4: $ITEMS_JSON: transports[$_i] missing required field: $_f")
        fi
      done
    done

    # hotels[] required fields
    _hc=$(jq '.hotels | length' "$ITEMS_JSON" 2>/dev/null || echo 0)
    for ((_i=0; _i<_hc; _i++)); do
      for _f in city_type days invoice_type invoice_no amount; do
        _v=$(jq -r ".hotels[$_i].$_f // empty" "$ITEMS_JSON")
        if [[ -z "$_v" ]]; then
          errors+=("[FAIL] Phase 4: $ITEMS_JSON: hotels[$_i] missing required field: $_f")
        fi
      done
    done

    # subsidies[] required fields
    _sc=$(jq '.subsidies | length' "$ITEMS_JSON" 2>/dev/null || echo 0)
    for ((_i=0; _i<_sc; _i++)); do
      for _f in days tool official_car_pickup hosted_by_counterparty; do
        _v=$(jq -r ".subsidies[$_i].$_f // empty" "$ITEMS_JSON")
        if [[ -z "$_v" ]]; then
          errors+=("[FAIL] Phase 4: $ITEMS_JSON: subsidies[$_i] missing required field: $_f")
        fi
      done
    done
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
fi

# --- Report ---
if [[ ${#errors[@]} -gt 0 ]]; then
  printf '%s\n' "${errors[@]}" >&2
  exit 1
fi
exit 0
