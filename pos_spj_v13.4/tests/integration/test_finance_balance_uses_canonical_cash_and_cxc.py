"""Regresión: KPIs de Finanzas (balance_general) leen las fuentes canónicas.

Bug reportado en validación manual: "Finanzas sigue sin cargar KPIs".
Causa: balance_general leía SOLO treasury_ledger / accounts_receivable
(vacías) mientras el POS escribe efectivo en movimientos_caja y la CxC de
ventas a crédito en cuentas_por_cobrar.
"""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.services.finance.treasury_service import TreasuryService
from tests.integration._born_clean_db import make_db


def test_balance_caja_includes_operating_cash():
    conn = make_db()
    turno = new_uuid()
    for tipo, monto in (("VENTA", 500.0), ("INGRESO", 100.0), ("RETIRO", 150.0)):
        conn.execute(
            "INSERT INTO movimientos_caja (id, turno_id, sucursal_id, tipo, monto, "
            " concepto, usuario) VALUES (?, ?, ?, ?, ?, 'test', 'u')",
            (new_uuid(), turno, new_uuid(), tipo, monto),
        )

    bal = TreasuryService(conn).balance_general()
    # 500 + 100 − 150 = 450 de efectivo operativo (treasury_ledger vacío)
    assert bal["activo"]["caja_bancos"] == 450.0


def test_balance_cxc_includes_cuentas_por_cobrar():
    conn = make_db()
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, venta_id, folio, "
        " monto_original, saldo_pendiente, estado) "
        "VALUES (?, ?, ?, 'F-1', 750.0, 750.0, 'pendiente')",
        (new_uuid(), new_uuid(), new_uuid()),
    )
    bal = TreasuryService(conn).balance_general()
    assert bal["activo"]["cuentas_cobrar"] == 750.0


def test_balance_survives_empty_optional_tables():
    conn = make_db()
    bal = TreasuryService(conn).balance_general()
    assert bal["activo"]["caja_bancos"] == 0.0
    assert bal["activo"]["cuentas_cobrar"] == 0.0
