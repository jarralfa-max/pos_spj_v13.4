"""POS-19 — the Sales/POS decomposed UI never executes raw SQL. Mirrors
`tests/architecture/test_customers_crm_ui_has_no_sql.py`. SQL belongs only
in `backend/infrastructure/db/repositories/`; UI components call
`SalesPosPresenter` methods only.
"""

from __future__ import annotations

import re

from .sales_pos_guardrails import SALES_POS_UI_ROOT, relative, sales_pos_ui_py_files

_SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|DROP\s+TABLE|CREATE\s+TABLE|PRAGMA)\b",
    re.IGNORECASE,
)
_EXECUTE_CALL = re.compile(r"\.(execute|executemany)\s*\(")


def test_sales_pos_ui_has_no_raw_sql():
    offenders = []
    for path in sales_pos_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _SQL_KEYWORDS.search(line) or _EXECUTE_CALL.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"Raw SQL / .execute() found under {relative(SALES_POS_UI_ROOT)} — the UI must "
        "call the presenter, never the database:\n" + "\n".join(offenders)
    )
