# Preflight Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-flight validation script (`preflight_check.sh`) that verifies all input data is complete before the login + reimbursement pipeline runs.

**Architecture:** Standalone bash script using jq for JSON validation. 5 sequential phases accumulate errors and report all at once to stderr. SKILL.md gains §1.2 requiring the script pass before §2 login.

**Tech Stack:** Bash, jq

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `scripts/preflight_check.sh` | Pre-flight validation (5 phases) |
| Create | `tests/test_preflight_check.sh` | Bash test suite for preflight |
| Modify | `SKILL.md:68-69` | Insert §1.2 between §1.1 and §2 |

---

### Task 1: Create test suite

**Files:**
- Create: `tests/test_preflight_check.sh`

- [ ] **Step 1: Write the test script**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
PREFLIGHT="$SCRIPT_DIR/scripts/preflight_check.sh"

pass=0 fail=0

assert_fail() {
  local desc="$1"
  local expected_pattern="${2:-}"
  local output rc
  output=$("$PREFLIGHT" 2>&1) && rc=0 || rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "FAIL: $desc (expected non-zero exit, got 0)"
    ((fail++))
  elif [[ -n "$expected_pattern" ]] && [[ "$output" != *"$expected_pattern"* ]]; then
    echo "FAIL: $desc (expected pattern not found)"
    echo "  pattern: $expected_pattern"
    echo "  output: $output"
    ((fail++))
  else
    echo "PASS: $desc"
    ((pass++))
  fi
}

assert_pass() {
  local desc="$1"
  local output rc
  output=$("$PREFLIGHT" 2>&1) && rc=0 || rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "FAIL: $desc (expected exit 0, got $rc)"
    echo "  output: $output"
    ((fail++))
  else
    echo "PASS: $desc"
    ((pass++))
  fi
}

# --- Setup: temp workspace with valid items JSON ---
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

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
  assert_fail "subsidy missing days" "subsidies[0].*days"
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

# T10: all valid, no attachments
(
  export SKILL_DIR="$SCRIPT_DIR"
  export ERM_ACCOUNT="test"
  export ACCOUNT_WORKSPACE="$TMPDIR"
  export ITEMS_JSON="$TMPDIR/items_valid.json"
  assert_pass "all valid data"
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

# --- Summary ---
echo ""
echo "Results: $pass passed, $fail failed"
[[ $fail -eq 0 ]]
```

- [ ] **Step 2: Make test script executable**

Run: `chmod +x tests/test_preflight_check.sh`

- [ ] **Step 3: Run tests to verify they fail (script doesn't exist yet)**

Run: `bash tests/test_preflight_check.sh`
Expected: errors about `preflight_check.sh` not found

- [ ] **Step 4: Commit test**

```bash
git add tests/test_preflight_check.sh
git commit -m "test: add preflight_check test suite"
```

---

### Task 2: Create preflight_check.sh

**Files:**
- Create: `scripts/preflight_check.sh`

Reuses patterns from `run_reimbursement_pipeline.sh`: `canonical_abs_path()`, `validate_workspace_path()`.

- [ ] **Step 1: Write the implementation**

```bash
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
```

- [ ] **Step 2: Make script executable**

Run: `chmod +x scripts/preflight_check.sh`

- [ ] **Step 3: Run tests to verify they pass**

Run: `bash tests/test_preflight_check.sh`
Expected: `Results: 11 passed, 0 failed`

- [ ] **Step 4: Commit**

```bash
git add scripts/preflight_check.sh
git commit -m "feat(skills): add preflight validation script"
```

---

### Task 3: Update SKILL.md with §1.2

**Files:**
- Modify: `SKILL.md:69` (insert after §1.1, before §2)

- [ ] **Step 1: Insert §1.2 after line 68 (end of §1.1)**

Insert between the end of §1.1 (line 68) and `## 2. 登录` (line 70):

```markdown

### 1.2 预检

执行预检脚本，验证所有输入数据齐全后再进入登录：

```bash
bash "${SKILL_DIR}/scripts/preflight_check.sh"
```

退出码 `0` 才进入 §2；失败时按 stderr 提示补全数据后重新执行 §1。

```

- [ ] **Step 2: Verify SKILL.md renders correctly**

Run: `cat skills/productivity/travel-reimbursement/SKILL.md | grep -A5 "1.2"`
Expected: shows the new section with code block and explanation

- [ ] **Step 3: Commit**

```bash
git add skills/productivity/travel-reimbursement/SKILL.md
git commit -m "docs(skills): add §1.2 preflight check step"
```

---

## Verification

End-to-end verification after all tasks complete:

1. **No env vars** → `bash scripts/preflight_check.sh` exits 1 with Phase 2 errors
2. **Valid setup** → exits 0 silently
3. **Missing JSON fields** → exits 1 with specific field names and indices
4. **Missing attachment** → exits 1 with file path
5. **Path isolation violation** → exits 1 with path details
6. **Full test suite** → `bash tests/test_preflight_check.sh` passes all 11 cases
7. **SKILL.md** → §1.2 appears between §1.1 and §2
