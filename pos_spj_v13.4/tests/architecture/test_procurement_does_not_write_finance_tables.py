"""PUR-13.11 — procurement never writes finance/cash tables directly.

A payable / payment is raised as a canonical event (PAYABLE_CREATED /
SUPPLIER_PAYMENT_SCHEDULED) consumed by the Finance/Treasury contexts. The
canonical procurement code must not INSERT/UPDATE cuentas_por_pagar,
movimientos_financieros, caja or tesorería, nor call legacy money mutators.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCUREMENT_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
]

_FINANCE = re.compile(
    r"INSERT\s+INTO\s+cuentas_por_pagar"
    r"|UPDATE\s+cuentas_por_pagar"
    r"|INSERT\s+INTO\s+accounts_payable"
    r"|INSERT\s+INTO\s+movimientos_financieros"
    r"|INSERT\s+INTO\s+pagos_compras"
    r"|crear_cuenta_por_pagar\s*\("
    r"|crear_cxp\s*\("
    r"|registrar_pago_proveedor\s*\("
    r"|pagar_proveedor\s*\(",
    re.IGNORECASE,
)
def _files():
    for root in PROCUREMENT_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_does_not_write_finance_tables():
    offenders = []
    for path in _files():
        text = path.read_text(encoding="utf-8")
        for m in _FINANCE.finditer(text):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "Compras no escribe finanzas/CxP directamente; emite PAYABLE_CREATED "
        "hacia el contexto Finance:\n" + "\n".join(offenders))
