"""Bug 7: el historial del cliente registra puntos ganados y usados por venta.

Fuente canónica loyalty_ledger (acumulacion/canje), no historico_puntos vacío.
"""
from __future__ import annotations

from application.services.loyalty_application_service import LoyaltyApplicationService
from backend.application.queries.customer_history_query_service import (
    CustomerHistoryQueryService,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _cliente(conn) -> str:
    cid = new_uuid()
    conn.execute("INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente', 1)", (cid,))
    return cid


def test_points_history_shows_earned_and_redeemed():
    conn = make_db()
    cid = _cliente(conn)
    venta1, venta2 = new_uuid(), new_uuid()
    svc = LoyaltyApplicationService(conn)

    svc.award_points_for_sale(cliente_id=cid, venta_id=venta1, puntos=50, usuario="cajera")
    svc.redeem_points_for_sale(cliente_id=cid, venta_id=venta2, puntos=20, usuario="cajera")

    history = CustomerHistoryQueryService(conn).get_points_history(cid)
    tipos = {h["tipo"] for h in history}
    assert "acumulacion" in tipos and "canje" in tipos

    ganados = next(h for h in history if h["tipo"] == "acumulacion")
    usados = next(h for h in history if h["tipo"] == "canje")
    assert ganados["puntos"] == 50 and ganados["venta_id"] == venta1
    assert usados["puntos"] == -20 and usados["venta_id"] == venta2


def test_points_history_empty_for_customer_without_movements():
    conn = make_db()
    cid = _cliente(conn)
    assert CustomerHistoryQueryService(conn).get_points_history(cid) == []


def test_points_history_reads_canonical_ledger_first():
    """Con loyalty_ledger presente, la fuente es esa (no historico_puntos)."""
    conn = make_db()
    cid = _cliente(conn)
    # Ruido en historico_puntos que NO debe aparecer si loyalty_ledger es la fuente
    conn.execute(
        "INSERT INTO historico_puntos (id, cliente_id, tipo, puntos, descripcion) "
        "VALUES (?, ?, 'legacy', 999, 'no canónico')",
        (new_uuid(), cid),
    )
    LoyaltyApplicationService(conn).award_points_for_sale(
        cliente_id=cid, venta_id=new_uuid(), puntos=10, usuario="u"
    )
    history = CustomerHistoryQueryService(conn).get_points_history(cid)
    assert all(h["puntos"] != 999 for h in history)
    assert any(h["puntos"] == 10 for h in history)
