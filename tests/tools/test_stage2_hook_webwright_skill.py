"""Contract test: stage2-hook wires the upstream Webwright skill via symlink."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE2_HOOK = REPO_ROOT / "docker" / "stage2-hook.sh"


@pytest.fixture(scope="module")
def stage2_text() -> str:
    if not STAGE2_HOOK.exists():
        pytest.skip("docker/stage2-hook.sh not present in this checkout")
    return STAGE2_HOOK.read_text()


def test_stage2_hook_links_webwright_skill_when_present(stage2_text: str) -> None:
    assert "/opt/webwright/skills/webwright" in stage2_text
    assert 'ln -sfn "$WEBWRIGHT_SKILL_SRC" "$webwright_skill_dest"' in stage2_text
    assert '[ -f "$WEBWRIGHT_SKILL_SRC/SKILL.md" ]' in stage2_text


def test_stage2_hook_skips_webwright_when_user_has_real_directory(stage2_text: str) -> None:
    assert "not a symlink); skipping" in stage2_text
