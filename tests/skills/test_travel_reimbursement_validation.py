"""Tests for travel-reimbursement skill validation helpers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills/productivity/travel-reimbursement"
SCRIPTS = SKILL_ROOT / "scripts"
SCRIPT_LIB = SCRIPTS / "lib"
PYTHONPATH_SKILL = f"{SCRIPT_LIB}:{SCRIPTS}"

sys.path.insert(0, str(SCRIPT_LIB))
from erm_travel_enums import VEHICLE_TO_PK  # noqa: E402


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


def _sample_items() -> dict:
    return {
        "summary": "北京出差",
        "training_fee": "否",
        "transports": [
            {
                "departure_date": "2026-05-04",
                "arrival_date": "2026-05-07",
                "vehicle": "火车（二等座）",
                "invoice_form": "火车电子报销凭证",
                "invoice_no": "T1",
                "amount": "500.00",
            }
        ],
        "subsidies": [
            {
                "days": "2",
                "tool": "火车",
                "official_car_pickup": "否",
                "hosted_by_counterparty": "否",
            }
        ],
    }


def test_validate_travel_items_enums_standalone_import():
    """Runnable without sourcing init.sh (SKILL documents direct invocation)."""
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validate_travel_items_enums.py"),
            "--items-json",
            str(SKILL_ROOT / "har" / "sample_items.json"),
        ],
        cwd=str(SCRIPTS),
        env={k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_validate_travel_items_enums_ok(tmp_path):
    items = tmp_path / "items.json"
    items.write_text(json.dumps(_sample_items()), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_travel_items_enums.py"), "--items-json", str(items)],
        cwd=str(SCRIPTS),
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_SKILL},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True


def test_validate_travel_items_enums_rejects_invoice_alias(tmp_path):
    data = _sample_items()
    data["hotels"] = [
        {
            "city_type": "其他人员/一般地区",
            "days": 1,
            "invoice_type": "普票",
            "invoice_no": "H1",
            "amount": "100.00",
        }
    ]
    items = tmp_path / "items.json"
    items.write_text(json.dumps(data), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_travel_items_enums.py"), "--items-json", str(items)],
        cwd=str(SCRIPTS),
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_SKILL},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 4
    err = json.loads(proc.stderr)
    assert err["error_code"] == "items_enum_invalid"
    assert any(i.get("field") == "invoice_type" for i in err["issues"])


def test_validate_travel_items_enums_rejects_unknown_vehicle(tmp_path):
    data = _sample_items()
    data["transports"][0]["vehicle"] = "高铁"
    items = tmp_path / "items.json"
    items.write_text(json.dumps(data), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_travel_items_enums.py"), "--items-json", str(items)],
        cwd=str(SCRIPTS),
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_SKILL},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 4
    err = json.loads(proc.stderr)
    assert err["error_code"] == "items_enum_invalid"
    assert err["issues"][0]["field"] == "vehicle"
    assert set(err["issues"][0]["suggestions"]).issubset(set(VEHICLE_TO_PK.keys()))


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
