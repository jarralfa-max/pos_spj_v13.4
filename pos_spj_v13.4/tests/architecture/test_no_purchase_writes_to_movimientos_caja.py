"""Compras NUNCA escriben en movimientos_caja.

Regla contable: Caja/POS solo representa dinero físico operativo de sucursal.
Las compras de inventario salen de capital/tesorería/banco o quedan como CxP.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT, collect_regex_violations

MOVIMIENTOS_CAJA_RE = re.compile(r"\bmovimientos_caja\b|registrar_movimiento_manual")

PURCHASE_PATHS = (
    APP_ROOT / "core" / "services" / "purchase_service.py",
    APP_ROOT / "core" / "use_cases" / "compra.py",
    APP_ROOT / "core" / "events" / "handlers" / "purchase_handler.py",
    APP_ROOT / "application" / "purchases",
    APP_ROOT / "repositories" / "purchase_repository.py",
    APP_ROOT / "backend" / "application" / "commands",
)


def test_no_purchase_writes_to_movimientos_caja() -> None:
    violations = collect_regex_violations(
        pattern=MOVIMIENTOS_CAJA_RE, roots=PURCHASE_PATHS
    )
    assert not violations, (
        "Rutas de Compras tocando Caja (movimientos_caja):\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )


def test_cash_service_rejects_purchase_movements() -> None:
    """La guarda canónica vive en CajaApplicationService."""
    path = APP_ROOT / "application" / "services" / "caja_application_service.py"
    text = path.read_text(encoding="utf-8")
    assert "Las compras no se registran desde Caja" in text
