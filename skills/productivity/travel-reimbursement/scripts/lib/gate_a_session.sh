#!/usr/bin/env bash
# Gate.A: export cookies from profile + HTTP probe. Requires erm_browser.sh sourced first.
# Uses: SKILL_DIR, PROFILE_DIR, ERM_SCRIPT_ROOT (from init.sh).

gate_a_cookie_from_json() {
  local cookies_json="$1"
  python3 "${ERM_SCRIPT_ROOT}/build_cookie_header.py" \
    --cookies-json "$cookies_json" 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('cookie_header',''))" 2>/dev/null \
    || true
}

gate_a_export_profile_cookies() {
  local out_json="$1"
  erm_browser_run --profile "$PROFILE_DIR" cookies get --json >"$out_json"
}

gate_a_probe() {
  local cookie="$1"
  python3 "${ERM_SCRIPT_ROOT}/probe_cookie_context.py" \
    --cookie "$cookie" --probe-msgtype-list
}

gate_a_probe_authenticated() {
  local probe_json="$1"
  echo "$probe_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['msgtype_list_probe']['looks_authenticated'])"
}

# Print cookie header; export from profile if COOKIE is empty.
gate_a_ensure_cookie() {
  local cookies_json="$1"
  if [[ -n "${COOKIE:-}" ]]; then
    printf '%s' "$COOKIE"
    return 0
  fi
  gate_a_export_profile_cookies "$cookies_json" || return $?
  local cookie
  cookie="$(gate_a_cookie_from_json "$cookies_json")"
  [[ -n "$cookie" ]] || return 1
  printf '%s' "$cookie"
}

# Echo probe JSON; exit 1 with stderr if not authenticated.
gate_a_require_authenticated() {
  local cookie="$1"
  local relogin_hint="$2"
  local probe
  probe="$(gate_a_probe "$cookie")"
  if [[ "$(gate_a_probe_authenticated "$probe")" != "True" ]]; then
    echo "Gate.A failed: cookie probe not authenticated" >&2
    echo "$probe" >&2
    echo "ERROR: ${relogin_hint}" >&2
    exit 1
  fi
  printf '%s' "$probe"
}

# Return 0 if session already valid (caller may exit login early).
gate_a_try_already_logged_in() {
  local cookies_json="$1"
  gate_a_export_profile_cookies "$cookies_json" || return $?
  local cookie probe
  cookie="$(gate_a_cookie_from_json "$cookies_json")"
  [[ -n "$cookie" ]] || return 1
  probe="$(gate_a_probe "$cookie")"
  [[ "$(gate_a_probe_authenticated "$probe")" == "True" ]] || return 1
  GATE_A_PROBE_JSON="$probe"
  GATE_A_COOKIE="$cookie"
  return 0
}
