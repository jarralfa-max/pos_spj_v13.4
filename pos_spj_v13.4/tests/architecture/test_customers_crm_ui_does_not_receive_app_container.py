"""CRM-1 (§4, §79) — the Clientes/CRM UI never receives the full AppContainer.

Legacy ``ModuloClientes.__init__`` accepts ``conexion`` and reaches into
``conexion.db``/``.container`` (see docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md
§1). The new module must take explicit, narrow dependencies (a presenter +
named view-models), never ``AppContainer`` wholesale. Reuses the same
``APPCONTAINER_RE`` idiom as ``architecture_guardrails.py``.
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import CRM_UI_ROOT, crm_ui_py_files, relative

_APPCONTAINER_RE = re.compile(
    r"\bAppContainer\b|\bself\.container\s*=\s*container\b|\bcontainer\s*=\s*container\b"
    r"|\bconexion\.db\b|\bconexion\.container\b",
)


def test_customers_crm_ui_does_not_receive_app_container():
    offenders = []
    for path in crm_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _APPCONTAINER_RE.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"AppContainer (or a container-shaped `conexion`) reached {relative(CRM_UI_ROOT)} — "
        "inject named dependencies explicitly instead:\n" + "\n".join(offenders)
    )
