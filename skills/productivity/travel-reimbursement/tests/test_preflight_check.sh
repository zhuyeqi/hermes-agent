#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
PREFLIGHT="$SCRIPT_DIR/scripts/preflight_check.sh"

RESULTS=$(mktemp)
trap 'rm -rf "$RESULTS"' EXIT

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

TMPROOT=$(mktemp -d)
trap 'rm -rf "$TMPROOT" "$RESULTS"' EXIT

# Valid items with dictionary keys (see har/sample_items.json)
valid_items='{
  "summary": "test trip",
  "transports": [{"departure_date":"2026-05-01","arrival_date":"2026-05-03","vehicle":"火车（二等座）","invoice_form":"火车电子报销凭证","invoice_no":"T1","amount":"100.00"}],
  "subsidies": [{"days":"2","tool":"火车","official_car_pickup":"否","hosted_by_counterparty":"否"}]
}'

setup_ws() {
  local account="${1:-test}"
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="$account"
  mkdir -p "$TMPROOT/$account"/{items,attachments,browser-profile}
  cd "$TMPROOT"
}

# T1: missing required env vars
(assert_fail "missing all env vars" "Phase 2")

# T2: ITEMS_JSON file not found
(
  setup_ws test
  export ITEMS_JSON="$TMPROOT/test/items/nonexistent.json"
  assert_fail "ITEMS_JSON file not found" "file not found"
)

# T3: invalid JSON
(
  setup_ws test
  echo "not json" > "$TMPROOT/test/items/bad.json"
  export ITEMS_JSON="$TMPROOT/test/items/bad.json"
  assert_fail "invalid JSON" "not valid JSON"
)

# T4: missing summary
(
  setup_ws test
  echo '{"transports":[{"departure_date":"2026-05-01","arrival_date":"2026-05-03","vehicle":"火车（二等座）","invoice_form":"火车电子报销凭证","invoice_no":"T1","amount":"1"}]}' > "$TMPROOT/test/items/no_summary.json"
  export ITEMS_JSON="$TMPROOT/test/items/no_summary.json"
  assert_fail "missing summary" "summary"
)

# T5: no transport/hotel/subsidy entries
(
  setup_ws test
  echo '{"summary":"x","transports":[],"hotels":[],"subsidies":[]}' > "$TMPROOT/test/items/empty.json"
  export ITEMS_JSON="$TMPROOT/test/items/empty.json"
  assert_fail "no expense entries" "at least one of"
)

# T6: transport missing required field
(
  setup_ws test
  echo '{"summary":"x","transports":[{"departure_date":"2026-05-01"}]}' > "$TMPROOT/test/items/bad_transport.json"
  export ITEMS_JSON="$TMPROOT/test/items/bad_transport.json"
  assert_fail "transport missing fields" "transports[0]"
)

# T7: subsidy missing days
(
  setup_ws test
  echo '{"summary":"x","subsidies":[{"tool":"火车","official_car_pickup":"否","hosted_by_counterparty":"否"}]}' > "$TMPROOT/test/items/no_days.json"
  export ITEMS_JSON="$TMPROOT/test/items/no_days.json"
  assert_fail "subsidy missing days" "subsidies[0]"
)

# T8: invalid enum (Phase 4b)
(
  setup_ws test
  echo '{"summary":"x","transports":[{"departure_date":"2026-05-01","arrival_date":"2026-05-03","vehicle":"高铁","invoice_form":"火车电子报销凭证","invoice_no":"T1","amount":"1"}]}' > "$TMPROOT/test/items/bad_enum.json"
  export ITEMS_JSON="$TMPROOT/test/items/bad_enum.json"
  assert_fail "invalid vehicle enum" "Phase 4b"
)

# T9: attachment file not found
(
  setup_ws test
  echo "$valid_items" > "$TMPROOT/test/items/valid.json"
  export ITEMS_JSON="$TMPROOT/test/items/valid.json"
  export ATTACHMENT_FILES="$TMPROOT/test/attachments/missing.pdf"
  assert_fail "attachment not found" "attachment not found"
)

# T10: path isolation violation
(
  setup_ws test
  mkdir -p /tmp/preflight_isolation_test
  echo "$valid_items" > /tmp/preflight_isolation_test/outside.json
  export ITEMS_JSON="/tmp/preflight_isolation_test/outside.json"
  assert_fail "path isolation violation" "outside ACCOUNT_WORKSPACE"
  rm -rf /tmp/preflight_isolation_test
)

# T11: subsidies only, no attachments (valid)
(
  setup_ws test
  echo '{"summary":"x","subsidies":[{"days":"1","tool":"火车","official_car_pickup":"否","hosted_by_counterparty":"否"}]}' > "$TMPROOT/test/items/subs_only.json"
  export ITEMS_JSON="$TMPROOT/test/items/subs_only.json"
  assert_pass "subsidies only, no attachments"
)

# T12: all valid with existing attachment
(
  setup_ws test
  echo "$valid_items" > "$TMPROOT/test/items/valid.json"
  touch "$TMPROOT/test/attachments/receipt.pdf"
  export ITEMS_JSON="$TMPROOT/test/items/valid.json"
  export ATTACHMENT_FILES="$TMPROOT/test/attachments/receipt.pdf"
  assert_pass "valid with attachment"
)

# T13: has transport but no attachments (should fail)
(
  setup_ws test
  echo "$valid_items" > "$TMPROOT/test/items/valid.json"
  export ITEMS_JSON="$TMPROOT/test/items/valid.json"
  assert_fail "invoices without attachments" "neither ATTACHMENT_FILE nor ATTACHMENT_FILES"
)

# T14: ATTACHMENT_FILE only (valid when transport present)
(
  setup_ws test
  echo "$valid_items" > "$TMPROOT/test/items/valid.json"
  touch "$TMPROOT/test/attachments/receipt.pdf"
  export ITEMS_JSON="$TMPROOT/test/items/valid.json"
  export ATTACHMENT_FILE="$TMPROOT/test/attachments/receipt.pdf"
  unset ATTACHMENT_FILES
  assert_pass "ATTACHMENT_FILE only with transport"
)

# T15: ATTACHMENT_FILE outside workspace
(
  setup_ws test
  echo "$valid_items" > "$TMPROOT/test/items/valid.json"
  mkdir -p /tmp/preflight_att_isolation
  touch /tmp/preflight_att_isolation/outside.pdf
  export ITEMS_JSON="$TMPROOT/test/items/valid.json"
  export ATTACHMENT_FILE="/tmp/preflight_att_isolation/outside.pdf"
  assert_fail "ATTACHMENT_FILE path isolation" "outside ACCOUNT_WORKSPACE"
  rm -rf /tmp/preflight_att_isolation
)

# T16: invalid ERM_ACCOUNT stays exit 1 (aggregated report, not exit 2)
(
  setup_ws test
  echo "$valid_items" > "$TMPROOT/test/items/valid.json"
  export ERM_ACCOUNT='../evil'
  export ITEMS_JSON="$TMPROOT/test/items/valid.json"
  assert_fail "invalid ERM_ACCOUNT" "plain account id"
)

pass=$(grep -c "^pass$" "$RESULTS") || true
fail=$(grep -c "^fail$" "$RESULTS") || true
echo ""
echo "Results: $pass passed, $fail failed"
[[ $fail -eq 0 ]]
