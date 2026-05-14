# Preflight Validation for Travel Reimbursement Skill

**Date**: 2026-05-14
**Status**: Draft
**Scope**: Add a pre-flight validation script to the travel-reimbursement skill

## Context

The travel reimbursement pipeline (login → form fill → submit) has 5 internal validation gates (A-E) that check server responses at runtime. However, missing input data (environment variables, incomplete JSON fields, absent attachment files) is only discovered after login and partial execution — wasting a browser session and forcing the user to restart from scratch.

A pre-flight check validates all input **before** any network or browser activity, failing fast with clear messages about what's missing.

## Design

### New File: `scripts/preflight_check.sh`

A standalone bash script using jq for JSON validation. Exit 0 on success, exit 1 with all errors reported to stderr.

#### Validation Phases

| Phase | Checks | Hard Stop |
|-------|--------|-----------|
| 1. Dependencies | `python3`, `jq`, `agent-browser` in PATH | Yes |
| 2. Environment | `SKILL_DIR`, `ERM_ACCOUNT`, `ACCOUNT_WORKSPACE`, `ITEMS_JSON` are set and non-empty | Yes |
| 3. Path Isolation | `ITEMS_JSON` resolves inside `ACCOUNT_WORKSPACE`; each `ATTACHMENT_FILES` path resolves inside `ACCOUNT_WORKSPACE` | Yes |
| 4. ITEMS_JSON | File exists, valid JSON, `summary` present, at least one of `transports`/`hotels`/`subsidies` non-empty; per-item required fields (see below) | Yes |
| 5. Attachments | Each file in colon-separated `ATTACHMENT_FILES` exists on disk (skip if var unset) | Yes |

#### Per-Item Required Fields

**transports[]**: `departure_date`, `arrival_date`, `vehicle`, `invoice_form`, `invoice_no`, `amount`

**hotels[]**: `city_type`, `days`, `invoice_type`, `invoice_no`, `amount`

**subsidies[]**: `days`, `tool`, `official_car_pickup`, `hosted_by_counterparty`

#### Output Format

- Success: `exit 0`, no stdout
- Failure: `exit 1`, stderr lists all errors collected:
  ```
  [FAIL] Phase 2: ERM_ACCOUNT is not set
  [FAIL] Phase 4: items/beijing.json: transports[1] missing required field: invoice_no
  [FAIL] Phase 4: items/beijing.json: subsidies[0] missing required field: days
  [FAIL] Phase 5: attachment not found: /path/to/missing.pdf
  ```

Errors are **accumulated** (all phases run), not short-circuited on first failure.

### SKILL.md Changes

Insert **§1.2 预检** after §1.1 (days inference):

```markdown
### 1.2 预检

执行 `bash "${SKILL_DIR}/scripts/preflight_check.sh"`。
退出码 0 才进入 §2；失败时按 stderr 提示补全数据后重新执行整个 §1。
```

### Explicitly Out of Scope

- Enum value validation (e.g. is `vehicle` a known type) — handled by pipeline Gate D
- Subsidy days inference from transport dates — handled by SKILL.md §1.1 before this script runs
- Browser profile directory validation — handled by login_erm.sh
- Network connectivity or ERM reachability checks

## Verification

1. Run `preflight_check.sh` with no env vars → exit 1, stderr lists missing vars
2. Run with valid env vars but missing ITEMS_JSON file → exit 1, reports missing file
3. Run with ITEMS_JSON missing required fields → exit 1, reports each missing field with index
4. Run with all valid data → exit 0, silent
5. Run with ATTACHMENT_FILES pointing to non-existent file → exit 1, reports missing attachment
6. Verify path isolation: ITEMS_JSON outside ACCOUNT_WORKSPACE → exit 1, reports path violation