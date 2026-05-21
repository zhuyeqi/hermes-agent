# reimbursement-process-unified 技能整改计划

> **For agentic workers:** 按 Task 顺序执行；每 Task 完成后跑 `scripts/run_tests.sh tests/skills/test_reimbursement_unified_validation.py` 与相关 bash `bash -n`。

**Goal:** 在保持现有行为（前置枚举校验、结构化错误、瘦身 Gate.A、browser chain）前提下，理清 `scripts/` 分层、去掉死代码、合并重复 Gate.A / browser 路径。

**Architecture:** 三入口不变（`preflight` → `login` → `pipeline`）；抽 `scripts/lib/` 放 bash/python 共享层；pipeline 专用步骤保留在 `scripts/` 根或 `scripts/steps/`；Agent 面仅文档约束，不新增 Agent 可调用脚本。

**Tech Stack:** bash、`agent-browser --profile`、`PYTHONPATH=scripts`、现有 pytest。

---

## 压缩上下文（实施前必读）

### 已完成的加固（本对话）

| 问题 | 对策 |
|------|------|
| 密码错误 AI 不知 | `classify_login_failure.py` + login stderr JSON |
| daemon/内存导致 browser 失败、AI 发散 | `erm_browser.sh`、`check_browser_health.sh`、`references/errors.md` 停机规则 |
| 发票枚举对但字典 key 错 | `erm_enums.py` + `validate_invoice_enums.py`；preflight 4b + pipeline 入口预检；save 仅 lookup |
| pipeline 频繁 daemon 错 | Gate.A 去掉 `login.jsp`+`networkidle`；`erm_browser_run_chained`；`AGENT_BROWSER_IDLE_TIMEOUT_MS=0` |

### 代码审查结论（引用未接错，结构偏杂）

- **清晰：** `erm_common` / `erm_enums` 单源；三入口；无循环依赖。
- **杂乱：** 扁平 `scripts/` 混入口、库、死代码；Gate.A cookie+probe 在 login/pipeline 重复；`check_browser_health` 与 `erm_browser_run` 双路径；`erm_report.py` 未接入。
- **孤儿：** `erm_report.py`、`merge_set_cookie_header.py`、`post_save_form.py`（repo 内无引用）。

### Agent 只允许直接调用

1. `preflight_check.sh`
2. `login_erm.sh`
3. `run_reimbursement_pipeline.sh`

其余均为内部实现。

---

## 目标目录（整改后）

```
reimbursement-process-unified/
├── SKILL.md
├── references/
│   ├── login.md
│   └── errors.md
└── scripts/
    ├── preflight_check.sh          # 入口
    ├── login_erm.sh                # 入口
    ├── run_reimbursement_pipeline.sh
    ├── lib/
    │   ├── resolve_python_env.sh
    │   ├── erm_browser.sh
    │   ├── gate_a_session.sh       # NEW: cookies + probe + 失败提示
    │   ├── erm_common.py
    │   └── erm_enums.py
    ├── validate_invoice_enums.py   # preflight + pipeline 调用
    ├── classify_login_failure.py
    ├── check_browser_health.sh     # 改：仅用 erm_browser_run
    ├── get_general_reimbursement_url.py
    ├── build_cookie_header.py
    ├── probe_cookie_context.py
    ├── extract_dispatch_defaults.py
    ├── upload_reimbursement_attachment.py
    ├── save_general_reimbursement_from_dispatch.py
    └── archive/                    # NEW: 非运行时
        ├── merge_set_cookie_header.py
        └── post_save_form.py
```

**不做的（YAGNI）：** 本计划不包含 `har/` 清理、差旅技能同步、目录 `steps/` 再拆（除非 Task 5 后仍觉必要）。

---

## Task 1: 抽离 Gate.A 共享 bash

**Files:**
- Create: `scripts/lib/gate_a_session.sh`
- Modify: `scripts/login_erm.sh`, `scripts/run_reimbursement_pipeline.sh`

- [ ] **Step 1:** 实现 `gate_a_export_cookie()`、`gate_a_probe_or_die()`（参数：`RUN_DIR` 可选、`COOKIE` 读写）
- [ ] **Step 2:** login 探针段与 pipeline Gate.A 改为 `source` + 调用
- [ ] **Step 3:** `bash -n` 两入口脚本

**验收：** login 已登录短路、pipeline 无 COOKIE 时导出 cookie 行为与改前一致。

---

## Task 2: 统一 browser 错误路径

**Files:**
- Modify: `scripts/check_browser_health.sh`, `scripts/lib/erm_browser.sh`（如需 `erm_browser_run` 支持 cookies 重定向）

- [ ] **Step 1:** `check_browser_health.sh` 在 `PROFILE_DIR` 存在时 `source erm_browser.sh`，用 `erm_browser_run --profile "$PROFILE_DIR" cookies get --json`
- [ ] **Step 2:** 删除重复的 grep/JSON 逻辑，失败时仍 exit 3
- [ ] **Step 3:** 手动跑 preflight Phase 1c

**验收：** daemon 失败时 stderr JSON 与 pipeline 一致（`error_code` 字段）。

---

## Task 3: 处理孤儿与半接入模块

**Files:**
- Move: `merge_set_cookie_header.py`, `post_save_form.py` → `scripts/archive/`
- Modify or Delete: `scripts/erm_report.py`
- Modify: `SKILL.md` 附录

- [ ] **Step 1:** 移入 `archive/`，各文件顶加注释「非运行时；维护者调试用」
- [ ] **Step 2:** **二选一**（实施时选 A）  
  - **A（推荐）：** 删除 `erm_report.py`；在 `erm_browser.sh` 顶部注释列出 exit code 与 `references/errors.md` 链接  
  - **B：** `erm_browser.sh` 的 `_erm_browser_emit_failure` 改为调用 `python3 -m erm_report`（需把模块挪到 lib 并调整 PYTHONPATH）
- [ ] **Step 3:** SKILL 附录增加「禁止 Agent 直接调用」列表 + `archive/` 说明

**验收：** `rg 'merge_set_cookie|post_save_form|erm_report' scripts/` 仅命中 archive 或注释。

---

## Task 4: 迁入 `scripts/lib/` 并修正引用

**Files:**
- Move: `resolve_python_env.sh`, `erm_browser.sh`, `erm_common.py`, `erm_enums.py` → `scripts/lib/`
- Modify: 所有 `source` / `PYTHONPATH` / `from erm_common` 路径

- [ ] **Step 1:** 移动文件；Python 在 `lib/` 内保持 `from erm_common import ...`（同目录）
- [ ] **Step 2:** 入口脚本改为 `source "${SKILL_DIR}/scripts/lib/resolve_python_env.sh"`，`PYTHONPATH="${SKILL_DIR}/scripts/lib:${SKILL_DIR}/scripts"`
- [ ] **Step 3:** 更新 `validate_invoice_enums.py` 的 import（`from erm_enums` 仍有效若 PYTHONPATH 含 lib）
- [ ] **Step 4:** `tests/skills/test_reimbursement_unified_validation.py` 的 `SCRIPTS` / `PYTHONPATH`

**验收：** `scripts/run_tests.sh tests/skills/test_reimbursement_unified_validation.py` 全绿；`bash -n` 全部 shell。

---

## Task 5: 文档与内联 Python 收敛（可选，本计划最后一轮）

**Files:**
- Modify: `run_reimbursement_pipeline.sh`, `references/errors.md`

- [ ] **Step 1:** 将 Gate B/C/D 的内联 `python3 - <<PY` 各抽为小脚本 **仅当** 单块 >40 行（否则保持，YAGNI）
- [ ] **Step 2:** `references/errors.md` 增加「目录结构」与「调用关系」简图
- [ ] **Step 3:** SKILL.md `version` bump + updated 日期

**验收：** 新同事仅读 SKILL + errors.md 能画出三入口数据流。

---

## 测试清单（每 Task 后）

```bash
scripts/run_tests.sh tests/skills/test_reimbursement_unified_validation.py -q
bash -n skills/productivity/reimbursement-process-unified/scripts/*.sh
bash -n skills/productivity/reimbursement-process-unified/scripts/lib/*.sh  # Task 4 后
```

有 ERM 环境时人工冒烟：

```bash
export SKILL_DIR=... ERM_ACCOUNT=... INVOICES_JSON=...
bash "$SKILL_DIR/scripts/preflight_check.sh"
# login + pipeline（勿提交凭据）
```

---

## 执行顺序与风险

| 顺序 | Task | 风险 |
|------|------|------|
| 1 | Task 1 Gate.A | 低；行为等价重构 |
| 2 | Task 2 browser 统一 | 低 |
| 3 | Task 3 孤儿 | 低；archive 不影响运行时 |
| 4 | Task 4 lib 迁移 | **中**；路径面广，需全量 grep |
| 5 | Task 5 文档 | 低 |

**建议 commit 粒度：** Task 1 一 commit，Task 2 一 commit，Task 3+4 可合并，Task 5 单独。

---

## 确认后开工

用户确认本计划后，从 **Task 1** 开始实施；若希望缩小范围，可只做 Task 1–3（不迁 `lib/` 目录）。
