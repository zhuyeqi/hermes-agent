#!/bin/sh
# Ensure agent-browser's expected chromium-<revision> dir exists under PLAYWRIGHT_BROWSERS_PATH.
# Primary fix: pin playwright in package-lock + `npx playwright install chromium` at image build.
# This script is the fallback when revision dirs drift (e.g. chromium-1223 installed, 1217 expected).
set -euo pipefail

ROOT="${PLAYWRIGHT_BROWSERS_PATH:-/opt/hermes/.playwright}"
EXPECTED="${PLAYWRIGHT_CHROMIUM_REVISION:-1217}"
TARGET="${ROOT}/chromium-${EXPECTED}"

if [ -e "$TARGET" ]; then
  echo "ensure-playwright-chromium-link: ok (exists ${TARGET})"
  exit 0
fi

ACTUAL="$(ls -d "${ROOT}"/chromium-* 2>/dev/null | head -1 || true)"
if [ -z "$ACTUAL" ]; then
  echo "ensure-playwright-chromium-link: no chromium-* under ${ROOT}" >&2
  exit 1
fi

echo "ensure-playwright-chromium-link: EXPECTED=chromium-${EXPECTED} ACTUAL=$(basename "$ACTUAL")"
ln -sf "$(basename "$ACTUAL")" "${ROOT}/chromium-${EXPECTED}"

if [ ! -e "$TARGET" ]; then
  echo "ensure-playwright-chromium-link: failed to create ${TARGET}" >&2
  exit 1
fi

echo "ensure-playwright-chromium-link: ok (${TARGET})"
