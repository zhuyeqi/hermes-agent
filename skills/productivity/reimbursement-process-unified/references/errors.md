# 结构化错误码与停机规则

脚本在 **stderr** 输出单行 JSON（`{"ok":false,"error_code":"...", ...}`）。Agent **必须**解析 `error_code`，按本表行动，**禁止**在下列情况下继续猜字段、改 API、或反复重试登录。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 登录/会话类失败 |
| 2 | 环境变量、快照解析、配置 |
| 3 | agent-browser / daemon 基础设施 |
| 4 | 发票 JSON / 枚举预检 |
| 5 | pipeline Gate 失败 |

## error_code 对照

| error_code | 典型原因 | Agent 必须 |
|------------|----------|------------|
| `wrong_password` | 用户名或密码错误 | **告知用户核对凭证**；勿自动重试密码 |
| `captcha_required` | 图形验证码 | 请用户浏览器手动登录一次，再跑 `login_erm.sh` |
| `session_conflict` | cookie probe 未认证、会话抢占 | 说明可能他处登录；重跑 login，勿改业务字段 |
| `login_failed` | 其他登录页错误 | 引用 `references/login.md`，向用户说明 |
| `env_missing` | 缺 SKILL_DIR / ERM_ACCOUNT / ERM_PASSWORD 等 | 补齐环境变量后重跑 |
| `snapshot_parse_failed` | 登录页结构/snapshot 异常 | `agent-browser --profile "$PROFILE_DIR" close` 后重试；仍失败则停机 |
| `browser_daemon_error` | daemon/内存/连接失败 | **停机**；向用户说明基础设施问题，建议 close/重启 |
| `browser_not_installed` | 未安装 CLI | 提示安装 agent-browser |
| `browser_command_failed` | 其他 browser 命令失败 | 先 close profile；勿发散改 pipeline |
| `invoice_enum_invalid` | expense_item / invoice_type 不在 `erm_enums.py` | **停机**；改 JSON 为字典精确 key（含 `allowed_expense_items` / `allowed_invoice_types`） |
| `invoice_json_invalid` | JSON 格式/缺字段 | 修复后重跑 `preflight_check.sh` |
| `gate_failed` | Gate.B–E | 读 `RUN_DIR` 产物；勿猜测 dispatch 字段 |

## 防发散（硬性）

1. **预检失败** → 只修预检指出的项，不跑 login/pipeline。
2. **exit 3** → 不尝试 savebill、不改发票枚举、不换账号 profile。
3. **wrong_password** → 不向用户索要密码以外的“ workaround ”。
4. **invoice_enum_invalid** → 不擅自用最相近枚举提交；须用户确认 `expense_item` 显示名与字典完全一致。
5. 脚本已输出 `error_code` 时，**不要**用浏览器手工完成本应脚本完成的步骤（除非 `captcha_required` 明确要求手动登录）。

## 浏览器 daemon 稳定性（login / preflight / pipeline）

- 技能脚本默认 `AGENT_BROWSER_IDLE_TIMEOUT_MS=0`，避免 httpx 阶段 daemon 自动退出。
- **login 开头探针**：`gate_a_try_already_logged_in` 经 `erm_browser_run cookies get`；daemon 失败 → **exit 3**（不进入填密码流程）。
- Gate.A 使用 `scripts/lib/gate_a_session.sh`（**不**打开 `login.jsp`）；抓 dispatch 用 `erm_browser_run_chained` + `wait --load load`。
- 连续失败：对该 `PROFILE_DIR` 执行一次 `agent-browser --profile "$PROFILE_DIR" close` 后再 `login_erm.sh`。

## 调用关系（简图）

```
preflight_check.sh → lib/{init,erm_workspace,resolve_python_env}.sh, check_browser_health.sh, validate_invoice_enums.py
login_erm.sh       → lib/{init,erm_workspace,erm_browser,gate_a_session,resolve_python_env}.sh
run_reimbursement_pipeline.sh → lib/* + scripts/*.py（save/get/upload/…）
```

## 相关脚本

- `scripts/lib/erm_browser.sh` — `erm_browser_run` / `erm_browser_run_chained`
- `scripts/lib/gate_a_session.sh` — Gate.A 共享逻辑
- `scripts/preflight_check.sh` — Phase 1c 浏览器、Phase 4b 枚举
- `scripts/check_browser_health.sh` — 单独探测 daemon
- `scripts/validate_invoice_enums.py` — 枚举与别名提示
- `scripts/classify_login_failure.py` — 登录 gate1 分类
- `scripts/login_erm.sh` — 登录失败 JSON
