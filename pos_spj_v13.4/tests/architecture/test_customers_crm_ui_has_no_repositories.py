"""CRM-1 (§13, §79) — the Clientes/CRM UI never talks to persistence directly.

No ``sqlite3`` import, no ``repositories.*`` import, no legacy ``core.db``
access, and no ``*Repository(`` instantiation inside
frontend/desktop/modules/customers_crm/. The UI consumes QueryServices/
UseCases only (mirrors test_transfers_ui_uses_design_system.py and
test_losses_sidebar_navigation.py's ``does_not_access_database_or_repositories``
checks for their own modules).
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import CRM_UI_ROOT, crm_ui_py_files, relative

_FORBIDDEN_TOKENS = ("sqlite3", "repositories.", "core.db", "container.db", "self.conexion")
_REPOSITORY_INSTANTIATION = re.compile(r"\b\w*Repository\s*\(")


def test_customers_crm_ui_does_not_access_database_or_repositories():
    offenders = []
    for path in crm_ui_py_files():
        source = path.read_text(encoding="utf-8")
        hits = [t for t in _FORBIDDEN_TOKENS if t in source]
        if _REPOSITORY_INSTANTIATION.search(source):
            hits.append("*Repository(")
        if hits:
            offenders.append(f"{relative(path)}: {hits}")
    assert not offenders, (
        f"Direct persistence access found under {relative(CRM_UI_ROOT)} — the UI "
        "must go through a QueryService/UseCase, never a repository:\n"
        + "\n".join(offenders)
    )
