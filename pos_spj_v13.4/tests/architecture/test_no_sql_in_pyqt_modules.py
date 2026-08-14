"""Prohibido SQL directo en módulos PyQt (modulos/, interfaz/, presentation/).

Alias obligatorio del bugfix skill sobre la misma regla de
test_no_sql_in_frontend.py: reusa la allowlist congelada. La deuda existente
no puede crecer; toda pantalla nueva debe leer vía QueryService.
"""

from __future__ import annotations

from .allowlists import SQL_IN_UI_ALLOWLIST
from .architecture_guardrails import (
    SQL_RE,
    UI_ROOTS,
    assert_no_new_violations,
    collect_regex_violations,
)


def test_no_sql_in_pyqt_modules() -> None:
    violations = collect_regex_violations(pattern=SQL_RE, roots=UI_ROOTS)
    assert_no_new_violations("SQL in PyQt modules", violations, SQL_IN_UI_ALLOWLIST)


# ``test_clientes_history_dialog_has_no_sql`` (asserted DialogoHistorialCliente
# had no raw SQL) was retired along with the class itself — the whole legacy
# modulos/clientes.py module (and its modulos/dialogs/cliente_*.py split
# from CRM-22) was deleted; the replacement,
# frontend/desktop/modules/customers_crm/pages/customer_profile_page.py, is
# already covered by the customers_crm CRM-1 no-raw-SQL guardrail suite.
