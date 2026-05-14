#!/usr/bin/env bash
set -euo pipefail

# ERM auto-login script: probe → login → verify.
#
# Required env:
#   SKILL_DIR   - path to this skill directory
#   PROFILE_DIR - agent-browser profile directory
#
# Optional env:
#   ERM_USERID    - required for fresh login (set via env before run)
#   ERM_PASSWORD  - required for fresh login (set via env before run)
#
# Exit codes:
#   0 - login successful (or already logged in)
#   1 - login failed (wrong password, probe false after submit, etc.)
#   2 - env missing / ERM_BASE_URL resolve failure / snapshot parse failure

die()  { echo "ERROR: $*" >&2; exit 1; }
die2() { echo "ERROR: $*" >&2; exit 2; }
step() { echo "== step: $*" >&2; }

require_env() {
  local k="$1"
  [[ -n "${!k:-}" ]] || die2 "missing env: $k"
}

require_env SKILL_DIR
require_env PROFILE_DIR

source "${SKILL_DIR}/scripts/resolve_python_env.sh"

ARTIFACT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/erm-login.XXXXXX")"
cleanup() { rm -rf "$ARTIFACT_DIR"; }
trap cleanup EXIT

ERM_BASE_URL="$(
  PYTHONPATH="${SKILL_DIR}/scripts" python3 -c "from erm_common import ERM_BASE_URL; print(ERM_BASE_URL)"
)"
[[ -n "$ERM_BASE_URL" ]] || die2 "failed to resolve ERM_BASE_URL"

# ---------------------------------------------------------------------------
# §2.1 Probe: already logged in?
# ---------------------------------------------------------------------------
step "probe_cookie_context"

agent-browser --profile "$PROFILE_DIR" cookies get --json > "$ARTIFACT_DIR/cookies.json"

COOKIE="$(python3 "$SKILL_DIR/scripts/build_cookie_header.py" \
  --cookies-json "$ARTIFACT_DIR/cookies.json" 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('cookie_header',''))" 2>/dev/null \
  || true)"

if [[ -z "$COOKIE" ]]; then
  step "no_valid_cookie, next step"
  ALREADY_AUTH="False"
else
  PROBE_JSON="$(python3 "$SKILL_DIR/scripts/probe_cookie_context.py" \
    --cookie "$COOKIE" --probe-msgtype-list)"

  ALREADY_AUTH="$(echo "$PROBE_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['msgtype_list_probe']['looks_authenticated'])")"
fi

if [[ "$ALREADY_AUTH" == "True" ]]; then
  echo "$PROBE_JSON" > "$ARTIFACT_DIR/probe.json"
  echo '{"status":"already_logged_in"}'
  step "already_logged_in"
  exit 0
fi

step "not_authenticated, please provide credentials"

if [[ -z "${ERM_USERID:-}" || -z "${ERM_PASSWORD:-}" ]]; then
  die2 "请提供账号(ERM_USERID)和密码(ERM_PASSWORD)，通过环境变量设置后重新运行。"
fi

# ---------------------------------------------------------------------------
# §2.2 Browser login
# ---------------------------------------------------------------------------

step "open_login_page"
agent-browser --profile "$PROFILE_DIR" open "${ERM_BASE_URL}/portal/app/mockapp/login.jsp?lrid=1"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

step "snapshot_and_parse_refs"
SNAPSHOT="$(agent-browser --profile "$PROFILE_DIR" snapshot -i)"

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

if [[ $? -ne 0 ]]; then
  die2 "failed to parse snapshot. Raw output:\n$SNAPSHOT"
fi

USERID_REF="$(echo "$REFS" | python3 -c "import json,sys;print(json.load(sys.stdin)['userid_ref'])")" || die2 "failed to parse refs JSON (userid_ref)"
PASSWORD_REF="$(echo "$REFS" | python3 -c "import json,sys;print(json.load(sys.stdin)['password_ref'])")" || die2 "failed to parse refs JSON (password_ref)"
SUBMIT_REF="$(echo "$REFS" | python3 -c "import json,sys;print(json.load(sys.stdin)['submit_ref'])")" || die2 "failed to parse refs JSON (submit_ref)"

step "fill_credentials userid_ref=@${USERID_REF} password_ref=@${PASSWORD_REF} submit_ref=@${SUBMIT_REF}"

agent-browser --profile "$PROFILE_DIR" fill "@${USERID_REF}" "$ERM_USERID"
agent-browser --profile "$PROFILE_DIR" fill "@${PASSWORD_REF}" "$ERM_PASSWORD"

unset ERM_USERID ERM_PASSWORD

step "click_submit"
agent-browser --profile "$PROFILE_DIR" click "@${SUBMIT_REF}"
agent-browser --profile "$PROFILE_DIR" wait --load networkidle

# ---------------------------------------------------------------------------
# §2.3 Verify login (two gates)
# ---------------------------------------------------------------------------
step "verify_login"

URL="$(agent-browser --profile "$PROFILE_DIR" get url)"
if echo "$URL" | grep -q "login.jsp"; then
  echo "ERROR: still on login page after submit (url=$URL)" >&2
  TIP="$(agent-browser --profile "$PROFILE_DIR" get text '#tiplabel' 2>/dev/null || true)"
  [[ -n "$TIP" ]] && echo "Page error: $TIP" >&2
  echo "See references/login.md for diagnosis." >&2
  exit 1
fi

step "gate1_ok url=$URL"

agent-browser --profile "$PROFILE_DIR" cookies get --json > "$ARTIFACT_DIR/cookies.json"
COOKIE="$(python3 "$SKILL_DIR/scripts/build_cookie_header.py" \
  --cookies-json "$ARTIFACT_DIR/cookies.json" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['cookie_header'])")"

PROBE_JSON="$(python3 "$SKILL_DIR/scripts/probe_cookie_context.py" \
  --cookie "$COOKIE" --probe-msgtype-list)"

AUTH_OK="$(echo "$PROBE_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['msgtype_list_probe']['looks_authenticated'])")"

if [[ "$AUTH_OK" != "True" ]]; then
  echo "ERROR: cookie probe says not authenticated" >&2
  echo "$PROBE_JSON" >&2
  echo "See references/login.md for diagnosis." >&2
  exit 1
fi

step "gate2_ok authenticated"

echo "$PROBE_JSON" > "$ARTIFACT_DIR/probe.json"
echo '{"status":"logged_in"}'
step "login_complete"
