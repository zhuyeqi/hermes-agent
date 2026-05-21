# Archive — not used at runtime

Maintainer / debug utilities only. Agent must **not** call these.

- `merge_set_cookie_header.py` — manual cookie merge experiments
- `post_save_form.py` — alternate save path; pipeline uses `save_general_reimbursement_from_dispatch.py`

Run from skill root with lib on `PYTHONPATH`, e.g.:

```bash
export PYTHONPATH="${SKILL_DIR}/scripts/lib:${SKILL_DIR}/scripts"
python3 "${SKILL_DIR}/scripts/archive/merge_set_cookie_header.py" ...
```
