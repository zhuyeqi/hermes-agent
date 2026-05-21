"""Classify ERM login gate-1 failures for structured agent feedback."""

from __future__ import annotations

import argparse
import json
import re
import sys


def classify(*, url: str = "", tip: str = "", page_text: str = "") -> dict[str, str]:
    combined = "\n".join(filter(None, [tip, page_text])).strip()
    lower = combined.lower()

    if "login.jsp" not in url and url and "login" not in url.lower():
        return {
            "error_code": "login_failed",
            "message": "登录后 URL 异常，需人工查看",
            "hint": "查看 references/login.md；勿自动重试密码",
        }

    password_patterns = (
        r"密码",
        r"口令",
        r"password",
        r"用户名或密码",
        r"账号.*错误",
        r"凭证",
        r"不正确",
        r"无效",
    )
    for pat in password_patterns:
        if re.search(pat, combined, re.I):
            if re.search(r"验证码|captcha|图形", combined, re.I):
                break
            return {
                "error_code": "wrong_password",
                "message": "用户名或密码错误（页面仍在登录页）",
                "hint": "向用户确认 ERM_ACCOUNT/ERM_PASSWORD 后重新运行 login_erm.sh；勿自动重试以免锁号",
            }

    if re.search(r"验证码|captcha|图形验证", combined, re.I):
        return {
            "error_code": "captcha_required",
            "message": "登录页出现图形验证码",
            "hint": "请用户在浏览器中手动登录一次，再重新运行 login_erm.sh",
        }

    if combined:
        return {
            "error_code": "login_failed",
            "message": f"登录失败：{combined[:200]}",
            "hint": "见 references/login.md；若为密码问题勿自动重试",
        }

    return {
        "error_code": "wrong_password",
        "message": "提交后仍停留在登录页（未获取到页面错误文案，按密码错误处理）",
        "hint": "向用户确认凭证；勿自动重试",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="")
    p.add_argument("--tip", default="")
    p.add_argument("--page-text", default="")
    args = p.parse_args()
    out = classify(url=args.url, tip=args.tip, page_text=args.page_text)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
