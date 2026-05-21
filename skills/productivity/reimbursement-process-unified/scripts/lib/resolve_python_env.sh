# resolve_python_env.sh — sourced fragment, NOT executable.
# Prepends the venv Python to PATH so all python3 calls use the right environment.
# Uses httpx as probe signal; no-op if current python3 already has it.
#
# Probe order:
#   1. Current python3 on PATH (fast path: activated venv, Docker)
#   2. /opt/hermes/.venv/bin/python3  (hermes-agent Docker)
#   3. /app/venv/bin/python3           (Open WebUI container)
#   4. ${SKILL_DIR}/../../../.venv/bin/python3  (local dev project root venv)

_resolve_python_env() {
  # Fast path: current python3 already has httpx.
  if python3 -c "import httpx" 2>/dev/null; then
    return 0
  fi

  local candidates=(
    "/app/venv/bin/python3"
    "/opt/hermes/.venv/bin/python3"
  )

  # Local dev: derive project root from SKILL_DIR.
  if [[ -n "${SKILL_DIR:-}" ]]; then
    local _proj_root
    _proj_root="$(cd "${SKILL_DIR}/../../.." 2>/dev/null && pwd)" || true
    if [[ -n "$_proj_root" ]]; then
      candidates+=("$_proj_root/.venv/bin/python3")
    fi
  fi

  for p in "${candidates[@]}"; do
    if [[ -x "$p" ]] && "$p" -c "import httpx" 2>/dev/null; then
      export PATH="$(dirname "$p"):${PATH}"
      echo "resolve_python_env: using $p (prepended to PATH)" >&2
      return 0
    fi
  done

  echo "ERROR: no Python with httpx found. Tried: python3 on PATH, ${candidates[*]}" >&2
  echo "Fix: activate the project venv, or install httpx: uv pip install httpx" >&2
  return 1
}

_resolve_python_env
