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


def test_clientes_history_dialog_has_no_sql() -> None:
    """El historial de Clientes lee vía CustomerHistoryQueryService."""
    from .architecture_guardrails import APP_ROOT, iter_source_lines

    path = APP_ROOT / "modulos" / "clientes.py"
    text = path.read_text(encoding="utf-8")
    marker = "class DialogoHistorialCliente"
    assert marker in text
    dialog_src = text.split(marker, 1)[1].split("\nclass ", 1)[0]
    for banned in ("cursor.execute", "SELECT fecha, total, metodo_pago", "id_cliente = ?"):
        assert banned not in dialog_src, (
            f"DialogoHistorialCliente aún contiene SQL directo: {banned!r}"
        )
    assert "CustomerHistoryQueryService" in text
