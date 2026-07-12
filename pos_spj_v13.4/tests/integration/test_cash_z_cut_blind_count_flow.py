"""Flujo de Corte Z ciego: conteo por denominaciones → corte → diferencia.

El cajero captura denominaciones sin ver el esperado; la diferencia se
calcula al confirmar, comparando efectivo contado contra efectivo esperado.
"""
from __future__ import annotations

from backend.application.services.cash_count_service import (
    compute_denomination_subtotals,
)
from backend.shared.ids import new_uuid
from core.services.enterprise.finance_service import FinanceService
from tests.integration._born_clean_db import make_db

DENOMINACIONES = [
    ("$500", 500), ("$200", 200), ("$100", 100), ("$50", 50), ("$20", 20),
]


def test_blind_count_flow_end_to_end():
    conn = make_db()
    fs = FinanceService(conn)
    sucursal_id, usuario = new_uuid(), "cajera"
    turno_id = fs.abrir_turno(sucursal_id, usuario, 200.0)

    # Ventas del turno: 700 en efectivo, 300 con tarjeta
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, usuario, total, forma_pago, "
        " efectivo_recibido, estado, fecha) "
        "VALUES (?, 'F-A', ?, ?, 700.0, 'Efectivo', 700.0, 'completada', "
        " datetime('now','+1 second'))",
        (new_uuid(), sucursal_id, usuario),
    )
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, usuario, total, forma_pago, "
        " estado, fecha) "
        "VALUES (?, 'F-B', ?, ?, 300.0, 'Tarjeta', 'completada', "
        " datetime('now','+1 second'))",
        (new_uuid(), sucursal_id, usuario),
    )

    # Conteo ciego: 1×500 + 1×200 + 1×100 + 2×50 = 900 contados
    conteo = {500: 1, 200: 1, 100: 1, 50: 2}
    subtotales, total_contado = compute_denomination_subtotals(DENOMINACIONES, conteo)
    assert subtotales[50] == 100.0
    assert total_contado == 900.0

    resultado = fs.generar_corte_z(turno_id, sucursal_id, usuario, total_contado)

    # esperado = fondo 200 + efectivo 700 = 900 (la tarjeta NO cuenta)
    assert resultado["efectivo_esperado"] == 900.0
    assert resultado["efectivo_contado"] == 900.0
    assert resultado["diferencia"] == 0.0

    turno = conn.execute(
        "SELECT estado, efectivo_esperado, efectivo_contado, diferencia "
        "FROM turnos_caja WHERE id=?",
        (turno_id,),
    ).fetchone()
    assert turno[0] == "cerrado"
    assert turno[1] == 900.0 and turno[2] == 900.0 and turno[3] == 0.0
