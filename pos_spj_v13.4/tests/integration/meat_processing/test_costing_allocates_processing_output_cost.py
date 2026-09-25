"""§12/§13/§25 — Costos reparte el costo de lo consumido entre lo producido, lo
guarda como SU asignación y publica los hechos: el costo por salida (Precios) y
el hecho contable de la producción (Finanzas), que Finanzas asienta cuadrado.

Canal bovina: 100 kg a 100/kg = 10 000 repartidos por valor de venta relativo.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.costing.wiring import dispatch_costing_outbox
from backend.domain.finance.enums import PostingPurpose
from backend.domain.meat_processing.enums import ProcessType
from backend.infrastructure.db.repositories.costing.processing_cost_repository import (
    ProcessingCostRepository,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from tests.integration.meat_processing._generic_plant import (
    Planta,
    build_db,
    bus_with_real_wiring,
)


@pytest.fixture()
def canal():
    conn = build_db()
    p = Planta(conn)
    bovino = p.especie("Bovino")
    fuente = p.producto("Canal bovina", lote=True, especie=bovino)
    lomo = p.producto("Lomo bovino", lote=True, especie=bovino)
    falda = p.producto("Falda", lote=True, especie=bovino)
    hueso = p.producto("Hueso", especie=bovino)
    p.despiece(fuente, [(lomo, "MAIN_PRODUCT", "0.30"), (falda, "CO_PRODUCT", "0.50"),
                        (hueso, "WASTE", "0.20")], especie=bovino)
    p.costo(fuente, "100")
    p.precio(lomo, "300"); p.precio(falda, "120")
    p.existencia(fuente, "150", lote="CANAL-01", vence="2031-01-01")
    oid = p.lista(ProcessType.DISASSEMBLY, fuente, "100")
    yield p, oid, fuente, lomo, falda, hueso
    conn.close()


def test_costing_allocates_the_whole_input_cost_by_relative_sales_value(canal):
    p, oid, fuente, lomo, falda, hueso = canal
    assert p.ejecutar(oid, {lomo: "30", falda: "50", hueso: "20"}).success

    asignacion = ProcessingCostRepository(p.conn).get_by_order(oid)
    assert asignacion.method == "RELATIVE_SALES_VALUE"
    assert asignacion.input_cost_total == Decimal("10000.00")
    salidas = {l.product_id: l for l in asignacion.lines if l.line_kind == "OUTPUT"}
    # 30×300 = 9000 ; 50×120 = 6000 → 60 % / 40 %
    assert salidas[lomo].allocated_cost == Decimal("6000.00")
    assert salidas[falda].allocated_cost == Decimal("4000.00")
    assert salidas[hueso].allocated_cost == Decimal("0")
    assert salidas[lomo].unit_cost == Decimal("200.0000")
    [insumo] = [l for l in asignacion.lines if l.line_kind == "INPUT"]
    assert insumo.product_id == fuente and insumo.lot_id


def test_close_costing_finance_chain_posts_a_balanced_production_entry(canal):
    """Cierre → Costos → PROCESSING_COST_ALLOCATED → Finanzas (asiento cuadrado)."""
    p, oid, fuente, lomo, falda, hueso = canal
    bus = bus_with_real_wiring(p.conn)
    r = p.ejecutar(oid, {lomo: "30", falda: "50", hueso: "20"},
                   dispatch=lambda conn: dispatch_costing_outbox(conn, bus))
    assert r.success, r.message

    with FinanceUnitOfWork(p.conn) as uow:
        asiento = uow.journal_entries.find_by_posting_reference(
            "production", oid, PostingPurpose.PRODUCTION)
    assert asiento is not None and asiento.is_balanced()
    assert asiento.total_credits().to_string() == "10000.00"
    pendientes = p.conn.execute(
        "SELECT COUNT(*) FROM costing_outbox WHERE status <> 'DISPATCHED'").fetchone()[0]
    assert pendientes == 0


def test_without_a_consumer_the_financial_fact_stays_pending(canal):
    """Estricto: un hecho con impacto contable que nadie atendió no se da por
    entregado."""
    from backend.shared.events.application_bus import ApplicationEventBus

    p, oid, fuente, lomo, falda, hueso = canal
    vacio = ApplicationEventBus()
    assert p.ejecutar(oid, {lomo: "30", falda: "50", hueso: "20"},
                      dispatch=lambda conn: dispatch_costing_outbox(conn, vacio)).success
    estados = {r[0] for r in p.conn.execute("SELECT status FROM costing_outbox")}
    assert "DISPATCHED" not in estados
