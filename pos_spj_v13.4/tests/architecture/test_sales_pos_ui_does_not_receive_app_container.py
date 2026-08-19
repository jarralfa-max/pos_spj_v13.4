"""POS-19 — the Sales/POS decomposed UI never receives the full
AppContainer. Legacy `ModuloVentas.__init__` accepts `container` and reaches
into it directly (`self.container = container`) — the new module must take
explicit, narrow dependencies (a presenter), never `AppContainer` wholesale.
Mirrors `tests/architecture/test_customers_crm_ui_does_not_receive_app_container.py`.
"""

from __future__ import annotations

import re

from .sales_pos_guardrails import SALES_POS_UI_ROOT, relative, sales_pos_ui_py_files

_APPCONTAINER_RE = re.compile(
    r"\bAppContainer\b|\bself\.container\s*=\s*container\b|\bcontainer\s*=\s*container\b",
)


def test_sales_pos_ui_does_not_receive_app_container():
    offenders = []
    for path in sales_pos_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _APPCONTAINER_RE.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"AppContainer reached {relative(SALES_POS_UI_ROOT)} — "
        "inject a presenter explicitly instead:\n" + "\n".join(offenders)
    )
