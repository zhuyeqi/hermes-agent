"""Tests for reimbursement-process-unified skill validation helpers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills/productivity/reimbursement-process-unified"
SCRIPTS = SKILL_ROOT / "scripts"
SCRIPT_LIB = SCRIPTS / "lib"
PYTHONPATH_SKILL = f"{SCRIPT_LIB}:{SCRIPTS}"

sys.path.insert(0, str(SCRIPT_LIB))
from erm_enums import EXPENSE_ITEM_TO_PK  # noqa: E402


def _run_classify(**kwargs: str) -> dict:
    args = [sys.executable, str(SCRIPTS / "classify_login_failure.py")]
    for k, v in kwargs.items():
        args.extend([f"--{k.replace('_', '-')}", v])
    proc = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def test_classify_wrong_password():
    out = _run_classify(url="http://x/login.jsp", tip="用户名或密码错误")
    assert out["error_code"] == "wrong_password"
    assert "ERM_ACCOUNT" in out["hint"]
    assert "ERM_USERID" not in out["hint"]


def test_classify_captcha():
    out = _run_classify(url="http://x/login.jsp", tip="请输入图形验证码")
    assert out["error_code"] == "captcha_required"


def test_validate_invoice_enums_ok(tmp_path):
    inv = tmp_path / "invoices.json"
    inv.write_text(
        json.dumps(
            [
                {
                    "amount": "60",
                    "tax_amount": "6",
                    "vat_amount": "66",
                    "invoice_no": "1",
                    "expense_item": "党建工作经费",
                    "invoice_type": "增值税普通发票",
                }
            ]
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_invoice_enums.py"), "--invoices-json", str(inv)],
        cwd=str(SCRIPTS),
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_SKILL},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True


def test_validate_invoice_enums_rejects_invoice_alias(tmp_path):
    inv = tmp_path / "invoices.json"
    inv.write_text(
        json.dumps(
            [
                {
                    "amount": "60",
                    "tax_amount": "6",
                    "vat_amount": "66",
                    "invoice_no": "1",
                    "expense_item": "党建工作经费",
                    "invoice_type": "普票",
                }
            ]
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_invoice_enums.py"), "--invoices-json", str(inv)],
        cwd=str(SCRIPTS),
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_SKILL},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 4
    err = json.loads(proc.stderr)
    assert err["error_code"] == "invoice_enum_invalid"
    assert any(i.get("field") == "invoice_type" for i in err["issues"])
    assert "allowed_expense_items" in err


def test_validate_invoice_enums_rejects_unknown_expense(tmp_path):
    inv = tmp_path / "invoices.json"
    inv.write_text(
        json.dumps(
            [
                {
                    "amount": "60",
                    "tax_amount": "6",
                    "vat_amount": "66",
                    "invoice_no": "1",
                    "expense_item": "不存在的费用",
                    "invoice_type": "增值税普通发票",
                }
            ]
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_invoice_enums.py"), "--invoices-json", str(inv)],
        cwd=str(SCRIPTS),
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_SKILL},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 4
    err = json.loads(proc.stderr)
    assert err["error_code"] == "invoice_enum_invalid"
    assert err["issues"][0]["field"] == "expense_item"
    assert "suggestions" in err["issues"][0]
    allowed = err["allowed_expense_items"]
    assert len(allowed) >= 1
    assert set(allowed) == set(EXPENSE_ITEM_TO_PK.keys())
    assert "党建工作经费" in allowed
    assert set(err["issues"][0]["suggestions"]).issubset(set(allowed))


def _run_erm_resolve_workspace(*, account: str, cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = {
        **dict(__import__("os").environ),
        "ERM_ACCOUNT": account,
        "PWD": str(cwd),
    }
    if extra_env:
        env.update(extra_env)
    script = (
        f"source {SCRIPT_LIB / 'erm_workspace.sh'} && "
        "erm_resolve_workspace && "
        'printf "ACCOUNT_WORKSPACE=%s\\nPROFILE_DIR=%s\\n" "$ACCOUNT_WORKSPACE" "$PROFILE_DIR"'
    )
    return subprocess.run(
        ["bash", "-c", script],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_erm_resolve_workspace_paths(tmp_path):
    proc = _run_erm_resolve_workspace(account="testuser", cwd=tmp_path)
    lines = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())
    assert lines["ACCOUNT_WORKSPACE"] == str(tmp_path / "testuser")
    assert lines["PROFILE_DIR"] == str(tmp_path / "testuser" / "browser-profile")


@pytest.mark.parametrize("bad_account", ["../evil", "user/sub", "a..b"])
def test_erm_resolve_workspace_rejects_invalid_account(tmp_path, bad_account: str):
    proc = subprocess.run(
        [
            "bash",
            "-c",
            f"source {SCRIPT_LIB / 'erm_workspace.sh'} && erm_resolve_workspace",
        ],
        cwd=str(tmp_path),
        env={
            **dict(__import__("os").environ),
            "ERM_ACCOUNT": bad_account,
            "PWD": str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "ERM_ACCOUNT" in proc.stderr


def test_erm_resolve_workspace_ignores_stale_overrides(tmp_path):
    proc = _run_erm_resolve_workspace(
        account="testuser",
        cwd=tmp_path,
        extra_env={
            "ACCOUNT_WORKSPACE": "/wrong",
            "PROFILE_DIR": "/wrong/profile",
        },
    )
    lines = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())
    assert lines["ACCOUNT_WORKSPACE"] == str(tmp_path / "testuser")
    assert lines["PROFILE_DIR"] == str(tmp_path / "testuser" / "browser-profile")
