#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
PREFLIGHT="$SCRIPT_DIR/scripts/preflight_check.sh"

# Use a results file since subshells can't modify parent variables
RESULTS=$(mktemp)
trap 'rm -rf "$RESULTS"' EXIT

run_test() {
  local label="$1"
  shift
  local output rc
  output=$("$@" 2>&1) && rc=0 || rc=$?
  echo "$label|$rc|$output" >> "$RESULTS"
}

assert_fail() {
  local desc="$1"
  local expected_pattern="${2:-}"
  local output rc
  output=$("$PREFLIGHT" 2>&1) && rc=0 || rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "FAIL: $desc (expected non-zero exit, got 0)"
    echo "fail" >> "$RESULTS"
  elif [[ -n "$expected_pattern" ]] && [[ "$output" != *"$expected_pattern"* ]]; then
    echo "FAIL: $desc (expected pattern not found)"
    echo "  pattern: $expected_pattern"
    echo "  output: $output"
    echo "fail" >> "$RESULTS"
  else
    echo "PASS: $desc"
    echo "pass" >> "$RESULTS"
  fi
}

assert_pass() {
  local desc="$1"
  local output rc
  output=$("$PREFLIGHT" 2>&1) && rc=0 || rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "FAIL: $desc (expected exit 0, got $rc)"
    echo "  output: $output"
    echo "fail" >> "$RESULTS"
  else
    echo "PASS: $desc"
    echo "pass" >> "$RESULTS"
  fi
}

# --- Setup: temp workspace with valid items JSON ---
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR" "$RESULTS"' EXIT

valid_items='{
  "summary": "test trip",
  "transports": [{"departure_date":"2026-05-01","arrival_date":"2026-05-03","vehicle":"train","invoice_form":"receipt","invoice_no":"T1","amount":"100.00"}],
  "hotels": [{"city_type":"standard","days":2,"invoice_type":"vat","invoice_no":"H1","amount":"200.00"}],
  "subsidies": [{"days":2,"tool":"train","official_car_pickup":"no","hosted_by_counterparty":"no"}]
}'

echo "$valid_items" > "$TMPDIR/items_valid.json"

# --- Tests ---

# T1: missing required env vars
(assert_fail "missing all env vars" "Phase 2")

# T2: ITEMS_JSON file not found
(
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/nonexistent.json"
  assert_fail "ITEMS_JSON file not found" "file not found"
)

# T3: invalid JSON
(
  echo "not json" > "$TMPDIR/bad.json"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/bad.json"
  assert_fail "invalid JSON" "not valid JSON"
)

# T4: missing summary
(
  echo '{"transports":[{"departure_date":"2026-05-01","arrival_date":"2026-05-03","vehicle":"t","invoice_form":"r","invoice_no":"T1","amount":"1"}]}' > "$TMPDIR/no_summary.json"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/no_summary.json"
  assert_fail "missing summary" "summary"
)

# T5: no transport/hotel/subsidy entries
(
  echo '{"summary":"x","transports":[],"hotels":[],"subsidies":[]}' > "$TMPDIR/empty.json"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/empty.json"
  assert_fail "no expense entries" "at least one of"
)

# T6: transport missing required field
(
  echo '{"summary":"x","transports":[{"departure_date":"2026-05-01"}]}' > "$TMPDIR/bad_transport.json"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/bad_transport.json"
  assert_fail "transport missing fields" "transports[0]"
)

# T7: subsidy missing days
(
  echo '{"summary":"x","subsidies":[{"tool":"train","official_car_pickup":"no","hosted_by_counterparty":"no"}]}' > "$TMPDIR/no_days.json"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/no_days.json"
  assert_fail "subsidy missing days" "subsidies[0]"
)

# T8: attachment file not found
(
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/items_valid.json"
  export ATTACHMENT_FILES="$TMPDIR/missing.pdf"
  assert_fail "attachment not found" "attachment not found"
)

# T9: path isolation violation
(
  mkdir -p /tmp/preflight_isolation_test
  echo "$valid_items" > /tmp/preflight_isolation_test/outside.json
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="/tmp/preflight_isolation_test/outside.json"
  assert_fail "path isolation violation" "outside ACCOUNT_WORKSPACE"
  rm -rf /tmp/preflight_isolation_test
)

# T10: subsidies only, no attachments (valid — no invoices to attach)
(
  echo '{"summary":"x","subsidies":[{"days":1,"tool":"train","official_car_pickup":"no","hosted_by_counterparty":"no"}]}' > "$TMPDIR/subs_only.json"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/subs_only.json"
  assert_pass "subsidies only, no attachments"
)

# T11: all valid with existing attachment
(
  touch "$TMPDIR/receipt.pdf"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/items_valid.json"
  export ATTACHMENT_FILES="$TMPDIR/receipt.pdf"
  assert_pass "valid with attachment"
)

# T12: has transport/hotel but no attachments (should fail)
(
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/items_valid.json"
  assert_fail "invoices without attachments" "ATTACHMENT_FILES is not set"
)

# --- Summary ---
pass=$(grep -c "^pass$" "$RESULTS")  || true
fail=$(grep -c "^fail$" "$RESULTS")  || true
echo ""
echo "Results: $pass passed, $fail failed"
[[ $fail -eq 0 ]]
