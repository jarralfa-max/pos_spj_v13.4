"""Corte Z: el efectivo esperado excluye tarjeta, transferencia y crédito."""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.services.enterprise.finance_service import FinanceService
from tests.integration._born_clean_db import make_db


def _abrir_turno(fs, sucursal_id, usuario, fondo=100.0):
    return fs.abrir_turno(sucursal_id, usuario, fondo)


def _venta(conn, sucursal_id, usuario, total, forma_pago, efectivo=0.0, cambio=0.0):
    conn.execute(
        "INSERT INTO ventas (id, folio, sucursal_id, usuario, total, forma_pago, "
        " efectivo_recibido, cambio, estado, fecha) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completada', datetime('now','+1 second'))",
        (new_uuid(), f"F-{total}", sucursal_id, usuario, total, forma_pago, efectivo, cambio),
    )


def test_expected_cash_excludes_non_cash_payments():
    conn = make_db()
    fs = FinanceService(conn)
    sucursal_id, usuario = new_uuid(), "caja1"
    turno_id = _abrir_turno(fs, sucursal_id, usuario, fondo=100.0)

    _venta(conn, sucursal_id, usuario, 200.0, "Efectivo", efectivo=200.0)
    _venta(conn, sucursal_id, usuario, 500.0, "Tarjeta")
    _venta(conn, sucursal_id, usuario, 300.0, "Transferencia")
    _venta(conn, sucursal_id, usuario, 400.0, "Crédito")
    # Mixto: 150 en efectivo (200 recibidos - 50 cambio) del total 250
    _venta(conn, sucursal_id, usuario, 250.0, "Pago Mixto", efectivo=200.0, cambio=50.0)

    resultado = fs.generar_corte_z(turno_id, sucursal_id, usuario, efectivo_fisico=450.0)

    # esperado = fondo 100 + efectivo 200 + porción mixta 150 = 450
    assert resultado["efectivo_esperado"] == 450.0
    assert resultado["diferencia"] == 0.0
    assert resultado["ventas_efectivo"] == 350.0
    # total_ventas sigue reportando todos los medios (informativo)
    assert resultado["total_ventas"] == 1650.0


def test_difference_detects_missing_cash_only():
    conn = make_db()
    fs = FinanceService(conn)
    sucursal_id, usuario = new_uuid(), "caja2"
    turno_id = _abrir_turno(fs, sucursal_id, usuario, fondo=0.0)

    _venta(conn, sucursal_id, usuario, 100.0, "Efectivo", efectivo=100.0)
    _venta(conn, sucursal_id, usuario, 900.0, "Tarjeta")

    resultado = fs.generar_corte_z(turno_id, sucursal_id, usuario, efectivo_fisico=80.0)
    assert resultado["efectivo_esperado"] == 100.0
    assert resultado["diferencia"] == -20.0   # faltante real de efectivo, no -920
