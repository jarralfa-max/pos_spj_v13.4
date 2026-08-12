"""CRM-1 (§13, §79) — the Clientes/CRM desktop UI never executes raw SQL.

Ratchet: frontend/desktop/modules/customers_crm/ has no files yet (CRM-1
baseline), so this passes vacuously. It fails the moment a .py file under
that module contains a SELECT/INSERT/UPDATE/DELETE/PRAGMA or a
``.execute(``/``.executemany(`` call — SQL belongs only in
backend/infrastructure/db/repositories/.
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import CRM_UI_ROOT, crm_ui_py_files, relative

_SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|DROP\s+TABLE|CREATE\s+TABLE|PRAGMA)\b",
    re.IGNORECASE,
)
_EXECUTE_CALL = re.compile(r"\.(execute|executemany)\s*\(")


def test_customers_crm_ui_has_no_raw_sql():
    offenders = []
    for path in crm_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _SQL_KEYWORDS.search(line) or _EXECUTE_CALL.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"Raw SQL / .execute() found under {relative(CRM_UI_ROOT)} — the UI must "
        "call a QueryService/UseCase, never the database:\n" + "\n".join(offenders)
    )
