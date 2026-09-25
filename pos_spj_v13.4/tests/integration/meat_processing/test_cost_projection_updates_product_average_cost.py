"""§12/§25 — el costo que asigna Costos llega al costo promedio del producto por
la ruta canónica (PRODUCTION_OUTPUT_COSTED → Precios), ponderado con lo que ya
había. Mezcla de carne (una sola salida: carga todo el costo)."""
from __future__ import annotations

from decimal import Decimal

from backend.application.costing.wiring import dispatch_costing_outbox
from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade
from backend.domain.meat_processing.enums import ProcessType
from tests.integration.meat_processing._generic_plant import (
    Planta,
    build_db,
    bus_with_real_wiring,
)


def _planta():
    conn = build_db()
    p = Planta(conn)
    res = p.producto("Carne de res")
    cerdo = p.producto("Carne de cerdo")
    mezcla = p.producto("Mezcla para chorizo")
    p.receta(mezcla, [(res, "0.5"), (cerdo, "0.5")])
    p.costo(res, "120"); p.costo(cerdo, "80")
    p.existencia(res, "100"); p.existencia(cerdo, "100")
    return p, res, cerdo, mezcla


def test_a_product_without_previous_cost_takes_the_production_cost():
    p, res, cerdo, mezcla = _planta()
    bus = bus_with_real_wiring(p.conn)
    oid = p.lista(ProcessType.MIXING, mezcla, "20")
    assert p.ejecutar(oid, {mezcla: "20"},
                      dispatch=lambda conn: dispatch_costing_outbox(conn, bus)).success
    # 10 kg × 120 + 10 kg × 80 = 2000 / 20 kg
    assert Decimal(str(PricingReadFacade(p.conn).unit_cost(mezcla, p.branch))) == Decimal("100")


def test_the_projection_is_a_weighted_average_with_existing_stock():
    p, res, cerdo, mezcla = _planta()
    bus = bus_with_real_wiring(p.conn)
    primera = p.lista(ProcessType.MIXING, mezcla, "20")
    assert p.ejecutar(primera, {mezcla: "20"},
                      dispatch=lambda conn: dispatch_costing_outbox(conn, bus)).success
    p.costo(res, "160"); p.costo(cerdo, "120")                 # sube la materia prima
    segunda = p.lista(ProcessType.MIXING, mezcla, "20")
    assert p.ejecutar(segunda, {mezcla: "20"},
                      dispatch=lambda conn: dispatch_costing_outbox(conn, bus)).success
    # (20 × 100 + 20 × 140) / 40
    assert Decimal(str(PricingReadFacade(p.conn).unit_cost(mezcla, p.branch))) == Decimal("120")


def test_without_dispatch_the_average_cost_is_not_touched():
    p, res, cerdo, mezcla = _planta()
    oid = p.lista(ProcessType.MIXING, mezcla, "20")
    assert p.ejecutar(oid, {mezcla: "20"}).success
    assert PricingReadFacade(p.conn).unit_cost(mezcla, p.branch) is None
