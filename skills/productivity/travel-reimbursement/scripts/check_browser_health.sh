#!/usr/bin/env bash
# Probe agent-browser daemon before login or pipeline. Exit 3 = infra.
set -euo pipefail

SKILL_DIR="${SKILL_DIR:-}"
PROFILE_DIR="${PROFILE_DIR:-}"

if [[ -z "$SKILL_DIR" ]]; then
  echo '{"ok":false,"error_code":"env_missing","message":"SKILL_DIR is not set"}' >&2
  exit 2
fi

# shellcheck source=lib/init.sh
source "${SKILL_DIR}/scripts/lib/init.sh"
# shellcheck source=lib/erm_browser.sh
source "${SKILL_DIR}/scripts/lib/erm_browser.sh"

if ! command -v agent-browser &>/dev/null; then
  echo '{"ok":false,"error_code":"browser_not_installed","message":"agent-browser CLI not found","hint":"npm install -g agent-browser && agent-browser install"}' >&2
  exit 3
fi

PROFILE_DIR="${PROFILE_DIR:-${TMPDIR:-/tmp}/erm-browser-health}"
export PROFILE_DIR
mkdir -p "$PROFILE_DIR"

_err_file="$(mktemp)"
_cleanup() { rm -f "$_err_file"; }
trap _cleanup EXIT

if ! erm_browser_run --profile "$PROFILE_DIR" cookies get --json >"$_err_file"; then
  exit 3
fi

echo '{"ok":true,"status":"browser_healthy"}'
exit 0
