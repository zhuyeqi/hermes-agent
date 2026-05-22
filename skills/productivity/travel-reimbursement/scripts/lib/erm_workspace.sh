#!/usr/bin/env bash
# Resolve per-account workspace paths from ERM_ACCOUNT only.
# Formula: ACCOUNT_WORKSPACE=$PWD/${ERM_ACCOUNT}, PROFILE_DIR=${ACCOUNT_WORKSPACE}/browser-profile
# Ignores any pre-set ACCOUNT_WORKSPACE / PROFILE_DIR in the environment.

erm_emit_env_missing() {
  local msg="$*"
  python3 -c 'import json,sys; print(json.dumps({"ok":false,"error_code":"env_missing","message":sys.argv[1]},ensure_ascii=False),file=sys.stderr)' "$msg" 2>/dev/null \
    || echo "ERROR: $msg" >&2
  exit 2
}

erm_require_account() {
  [[ -n "${ERM_ACCOUNT:-}" ]] || erm_emit_env_missing "missing env: ERM_ACCOUNT"
  if [[ "$ERM_ACCOUNT" == */* ]] || [[ "$ERM_ACCOUNT" == *..* ]]; then
    erm_emit_env_missing "ERM_ACCOUNT must be a plain account id (no / or ..)"
  fi
}

erm_resolve_workspace() {
  erm_require_account
  ACCOUNT_WORKSPACE="$PWD/${ERM_ACCOUNT}"
  PROFILE_DIR="${ACCOUNT_WORKSPACE}/browser-profile"
  export ACCOUNT_WORKSPACE PROFILE_DIR
}
