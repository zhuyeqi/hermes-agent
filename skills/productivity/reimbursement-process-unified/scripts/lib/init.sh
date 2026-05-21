#!/usr/bin/env bash
# Sourced from entry scripts after SKILL_DIR is set. Sets PYTHONPATH for lib + scripts.
[[ -n "${SKILL_DIR:-}" ]] || {
  echo "ERROR: SKILL_DIR required before sourcing init.sh" >&2
  return 1 2>/dev/null || exit 1
}
export ERM_SCRIPT_LIB="${SKILL_DIR}/scripts/lib"
export ERM_SCRIPT_ROOT="${SKILL_DIR}/scripts"
export PYTHONPATH="${ERM_SCRIPT_LIB}:${ERM_SCRIPT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
