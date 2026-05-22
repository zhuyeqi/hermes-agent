#!/usr/bin/env bash
# Sourced by entry scripts — do not execute directly.
# Wraps agent-browser; stderr JSON on failure.
#
# Exit codes (see references/errors.md):
#   0 ok | 1 login/session | 2 env/parse | 3 browser infra | 4 validation | 5 gate

erm_browser_init() {
  export AGENT_BROWSER_IDLE_TIMEOUT_MS="${AGENT_BROWSER_IDLE_TIMEOUT_MS:-0}"
}

_erm_browser_emit_failure() {
  local _combined="$1"
  local _argv="$2"
  local _code="browser_command_failed"
  local _hint='见 references/errors.md；勿猜测业务字段或改走手工填表'
  if echo "$_combined" | grep -Eqi 'daemon|ECONNREFUSED|connect.*refused|socket hang up|ENOMEM|out of memory|killed|Cannot connect|not running|EAGAIN|IPC'; then
    _code="browser_daemon_error"
    _hint="浏览器基础设施故障：向用户说明后停止。可尝试 agent-browser --profile \"${PROFILE_DIR:-}\" close 后重试"
  fi
  python3 -c '
import json, os, sys
print(json.dumps({
    "ok": False,
    "error_code": os.environ["CODE"],
    "message": "agent-browser 命令失败",
    "hint": os.environ["HINT"],
    "details": {"argv": os.environ.get("ARGV", ""), "stderr": os.environ.get("STDERR", "")[:800]},
}, ensure_ascii=False), file=sys.stderr)
' CODE="$_code" HINT="$_hint" ARGV="$_argv" STDERR="$_combined"
}

erm_browser_run() {
  erm_browser_init
  local _err
  _err="$(mktemp)"
  if agent-browser "$@" 2>"$_err"; then
    rm -f "$_err"
    return 0
  fi
  local _combined
  _combined="$(cat "$_err")"
  rm -f "$_err"
  _erm_browser_emit_failure "$_combined" "$*"
  return 3
}

erm_browser_run_chained() {
  erm_browser_init
  [[ -n "${PROFILE_DIR:-}" ]] || {
    echo '{"ok":false,"error_code":"env_missing","message":"PROFILE_DIR is not set"}' >&2
    return 2
  }
  local _err _full _part _qprofile
  _qprofile="$(printf '%q' "$PROFILE_DIR")"
  _full=""
  for _part in "$@"; do
    [[ -n "$_full" ]] && _full+=" && "
    _full+="agent-browser --profile ${_qprofile} ${_part}"
  done
  _err="$(mktemp)"
  if bash -c "$_full" 2>"$_err"; then
    rm -f "$_err"
    return 0
  fi
  local _combined
  _combined="$(cat "$_err")"
  rm -f "$_err"
  _erm_browser_emit_failure "$_combined" "$_full"
  return 3
}
