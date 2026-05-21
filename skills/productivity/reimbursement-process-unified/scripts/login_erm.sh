#!/usr/bin/env bash
set -euo pipefail

# ERM auto-login script: probe → login → verify.
#
# Required env:
#   SKILL_DIR    - path to this skill directory
#   ERM_ACCOUNT  - account id (login username + workspace dir name)
#
# Optional env:
#   ERM_PASSWORD - required for fresh login (set via env before run)
#
# Derived (do not set): ACCOUNT_WORKSPACE=$PWD/${ERM_ACCOUNT}, PROFILE_DIR=.../browser-profile
#
# Exit codes:
#   0 - login successful (or already logged in)
#   1 - login failed — stderr JSON error_code
#   2 - env missing / snapshot parse failure
#   3 - agent-browser daemon failure

die()  { echo "ERROR: $*" >&2; exit 1; }
die2() {
  local msg="$*"
  python3 -c 'import json,sys; print(json.dumps({"ok":false,"error_code":"env_missing","message":sys.argv[1]},ensure_ascii=False),file=sys.stderr)' "$msg" 2>/dev/null \
    || echo "ERROR: $msg" >&2
  exit 2
}
emit_login_error() {
  python3 "${ERM_SCRIPT_ROOT}/classify_login_failure.py" \
    --url "${1:-}" --tip "${2:-}" --page-text "${3:-}" \
    | python3 -c '
import json, sys
obj = json.load(sys.stdin)
obj["ok"] = False
print(json.dumps(obj, ensure_ascii=False), file=sys.stderr)
' || true
  exit 1
}
step() { echo "== step: $*" >&2; }

require_env() {
  local k="$1"
  [[ -n "${!k:-}" ]] || die2 "missing env: $k"
}

require_env SKILL_DIR
require_env ERM_ACCOUNT

# shellcheck source=lib/init.sh
source "${SKILL_DIR}/scripts/lib/init.sh"
# shellcheck source=lib/erm_workspace.sh
source "${ERM_SCRIPT_LIB}/erm_workspace.sh"
erm_resolve_workspace
# shellcheck source=lib/resolve_python_env.sh
source "${ERM_SCRIPT_LIB}/resolve_python_env.sh"
# shellcheck source=lib/erm_browser.sh
source "${ERM_SCRIPT_LIB}/erm_browser.sh"
# shellcheck source=lib/gate_a_session.sh
source "${ERM_SCRIPT_LIB}/gate_a_session.sh"

ARTIFACT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/erm-login.XXXXXX")"
cleanup() { rm -rf "$ARTIFACT_DIR"; }
trap cleanup EXIT

ERM_BASE_URL="$(
  python3 -c "from erm_common import ERM_BASE_URL; print(ERM_BASE_URL)"
)"
[[ -n "$ERM_BASE_URL" ]] || die2 "failed to resolve ERM_BASE_URL"

# ---------------------------------------------------------------------------
# §2.1 Probe: already logged in?
# ---------------------------------------------------------------------------
step "probe_cookie_context"

set +e
gate_a_try_already_logged_in "$ARTIFACT_DIR/cookies.json"
_probe_rc=$?
set -e
if [[ $_probe_rc -eq 0 ]]; then
  echo "$GATE_A_PROBE_JSON" > "$ARTIFACT_DIR/probe.json"
  echo '{"status":"already_logged_in"}'
  step "already_logged_in"
  exit 0
fi
if [[ $_probe_rc -eq 3 ]]; then
  exit 3
fi

step "not_authenticated, please provide credentials"

if [[ -z "${ERM_PASSWORD:-}" ]]; then
  die2 "请提供密码(ERM_PASSWORD)，并确保已设置 ERM_ACCOUNT，通过环境变量设置后重新运行。"
fi

# ---------------------------------------------------------------------------
# §2.2 Browser login
# ---------------------------------------------------------------------------

step "open_login_page"
erm_browser_run_chained \
  "open $(printf '%q' "${ERM_BASE_URL}/portal/app/mockapp/login.jsp?lrid=1")" \
  "wait --load networkidle" || exit $?

step "snapshot_and_parse_refs"
SNAPSHOT="$(erm_browser_run --profile "$PROFILE_DIR" snapshot -i)" || exit $?

set +e
REFS="$(echo "$SNAPSHOT" | python3 -c '
import re, sys, json

snapshot = sys.stdin.read()

elements = []
for m in re.finditer(r"-\s+(textbox|generic)\s+(?:\"([^\"]*)\"\s+)?\[ref=(e\d+)\]", snapshot):
    tag, text, ref = m.group(1), m.group(2) or "", m.group(3)
    elements.append({"tag": tag, "text": text, "ref": ref})

pwd_idx = None
for i, el in enumerate(elements):
    if el["tag"] == "generic" and "密码" in el["text"]:
        pwd_idx = i
        break

if pwd_idx is None:
    print("WARN: password label not found", file=sys.stderr)
    print(snapshot, file=sys.stderr)
    sys.exit(1)

userid_ref = None
for i in range(pwd_idx - 1, -1, -1):
    if elements[i]["tag"] == "textbox":
        userid_ref = elements[i]["ref"]
        break

password_ref = None
for i in range(pwd_idx + 1, len(elements)):
    if elements[i]["tag"] == "textbox":
        password_ref = elements[i]["ref"]
        break

if not userid_ref or not password_ref:
    print(f"WARN: userid_ref={userid_ref} password_ref={password_ref}", file=sys.stderr)
    print(snapshot, file=sys.stderr)
    sys.exit(1)

submit_ref = None
for el in elements:
    if el["tag"] == "generic" and "登录" in el["text"]:
        submit_ref = el["ref"]
        break

if not submit_ref:
    print("WARN: submit button not found", file=sys.stderr)
    print(snapshot, file=sys.stderr)
    sys.exit(1)

print(json.dumps({
    "userid_ref": userid_ref,
    "password_ref": password_ref,
    "submit_ref": submit_ref
}))
')"
_refs_rc=$?
set -e
if [[ $_refs_rc -ne 0 || -z "${REFS:-}" ]]; then
  python3 -c 'import json,sys; print(json.dumps({"ok":false,"error_code":"snapshot_parse_failed","message":"failed to parse login page snapshot","hint":"见 references/login.md；可 agent-browser close 后重试"},ensure_ascii=False),file=sys.stderr)'
  exit 2
fi

USERID_REF="$(echo "$REFS" | python3 -c "import json,sys;print(json.load(sys.stdin)['userid_ref'])")" || die2 "failed to parse refs JSON (userid_ref)"
PASSWORD_REF="$(echo "$REFS" | python3 -c "import json,sys;print(json.load(sys.stdin)['password_ref'])")" || die2 "failed to parse refs JSON (password_ref)"
SUBMIT_REF="$(echo "$REFS" | python3 -c "import json,sys;print(json.load(sys.stdin)['submit_ref'])")" || die2 "failed to parse refs JSON (submit_ref)"

step "fill_credentials userid_ref=@${USERID_REF} password_ref=@${PASSWORD_REF} submit_ref=@${SUBMIT_REF}"

erm_browser_run_chained \
  "fill $(printf '%q' "@${USERID_REF}") $(printf '%q' "$ERM_ACCOUNT")" \
  "fill $(printf '%q' "@${PASSWORD_REF}") $(printf '%q' "$ERM_PASSWORD")" \
  "click $(printf '%q' "@${SUBMIT_REF}")" \
  "wait --load networkidle" || exit $?

unset ERM_PASSWORD

step "click_submit_done"

# ---------------------------------------------------------------------------
# §2.3 Verify login (URL gate + cookie probe)
# ---------------------------------------------------------------------------
step "verify_login"

URL="$(erm_browser_run --profile "$PROFILE_DIR" get url)" || exit $?
if echo "$URL" | grep -q "login.jsp"; then
  TIP="$(erm_browser_run --profile "$PROFILE_DIR" get text '#tiplabel' 2>/dev/null || true)"
  emit_login_error "$URL" "$TIP" ""
fi

step "gate1_ok url=$URL"

gate_a_export_profile_cookies "$ARTIFACT_DIR/cookies.json" || exit $?
COOKIE="$(gate_a_cookie_from_json "$ARTIFACT_DIR/cookies.json")"
[[ -n "$COOKIE" ]] || die "failed to build cookie header after login"

PROBE_JSON="$(gate_a_require_authenticated "$COOKIE" "Re-login required — cookie probe failed after leaving login page; see references/login.md")"

step "gate2_ok authenticated"

echo "$PROBE_JSON" > "$ARTIFACT_DIR/probe.json"
echo '{"status":"logged_in"}'
step "login_complete"
