"""Plan de producción: la pantalla y las fuentes de sugerencias.

- Reposición: las sugerencias abiertas que calculó Inventario, sólo de
  productos PRODUCIBLES habilitados en la sucursal.
- Pronóstico: el motor de BI (`ProductionPlanningService`); sin historia de
  ventas no inventa nada y lo dice.
- La pantalla habilita lo que corresponde a cada estado y no muestra UUIDs.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases.replenishment_use_cases import (
    GenerateReplenishmentSuggestionsUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.application.meat_processing.queries.production_plan_query_service import (
    ProductionPlanQueryService,
)
from backend.application.meat_processing.use_cases import (
    AddProductionPlanLineUseCase,
    ApproveProductionPlanUseCase,
    CancelProductionPlanUseCase,
    ConvertProductionPlanLineUseCase,
    CreateProductionPlanUseCase,
    GenerateProductionPlanUseCase,
    RemoveProductionPlanLineUseCase,
    SubmitProductionPlanUseCase,
)
from backend.infrastructure.integrations.meat_processing_plan_sources import (
    ForecastPlanSource,
    ReplenishmentPlanSource,
)
from backend.infrastructure.integrations.meat_processing_ports import (
    ProcessingOrderFolioAdapter,
)
from backend.shared.ids import is_uuidv7, new_uuid
from frontend.desktop.modules.meat_processing.presenters.production_plan_presenter import (
    ProductionPlanPresenter,
)
from tests.integration.meat_processing._generic_plant import Planta, build_db

HOY = date(2026, 9, 25)


def _habilitar(conn, producto, branch):
    conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled)"
                 " VALUES (?,?,?,1)", (new_uuid(), producto, branch))
    conn.commit()


@pytest.fixture()
def planta():
    conn = build_db()
    p = Planta(conn)
    p.chorizo = p.producto("Chorizo")                      # producible
    p.refresco = p.producto("Refresco")                    # no producible
    conn.execute("UPDATE products SET producible=0 WHERE id=?", (p.refresco,))
    conn.commit()
    for producto in (p.chorizo, p.refresco):
        _habilitar(conn, producto, p.branch)
    yield p
    conn.close()


def _reponer(p, producto, disponible="2"):
    auth = InventoryAuthorizationPolicy.permissive_for_tests()
    if Decimal(disponible) > 0:
        p.existencia(producto, disponible)
    assert SetReplenishmentRuleUseCase(auth).execute(
        p.conn, product_id=producto, branch_id=p.branch, warehouse_id=p.warehouse,
        reorder_point=Decimal("10"), target_quantity=Decimal("30"),
        actor_user_id=p.gerente).success
    assert GenerateReplenishmentSuggestionsUseCase(auth).execute(
        p.conn, operation_id=new_uuid(), actor_user_id=p.gerente, branch_id=p.branch).success


def test_replenishment_suggests_only_producible_products(planta):
    _reponer(planta, planta.chorizo)
    _reponer(planta, planta.refresco)
    fuente = ReplenishmentPlanSource(planta.conn)
    sugeridas = fuente.suggestions(planta.branch)
    assert [s.product_name for s in sugeridas] == ["Chorizo"]
    assert sugeridas[0].source_type == "REPLENISHMENT"
    assert sugeridas[0].quantity > 0 and is_uuidv7(sugeridas[0].source_reference_id)


def test_without_open_replenishment_it_says_so(planta):
    fuente = ReplenishmentPlanSource(planta.conn)
    assert fuente.suggestions(planta.branch) == []
    assert "reposición" in fuente.note


def test_the_forecast_uses_the_bi_engine_and_maps_its_recommendation(planta, monkeypatch):
    llamadas = []

    class _Motor:
        def recommend_production(self, *, position, **kwargs):
            llamadas.append(position.product_id)
            return SimpleNamespace(recommended_production_quantity=Decimal("12"),
                                   expected_demand=Decimal("84"), priority="HIGH")

    fuente = ForecastPlanSource(planta.conn, today=HOY)
    monkeypatch.setattr(fuente, "_planning_service", lambda: _Motor())
    sugeridas = fuente.suggestions(planta.branch)
    assert llamadas == [planta.chorizo]                     # sólo producibles
    assert [(s.product_name, s.quantity, s.source_type) for s in sugeridas] == [
        ("Chorizo", Decimal("12"), "FORECAST")]


def test_without_sales_history_the_forecast_invents_nothing(planta):
    fuente = ForecastPlanSource(planta.conn, today=HOY)
    assert fuente.suggestions(planta.branch) == []
    assert fuente.note


# ── pantalla ─────────────────────────────────────────────────────────────────
def _presentador(p, usuario, *, fuentes=None):
    sesion = SimpleNamespace(user_id=usuario, active_branch_id=p.branch)
    auth = p.auth()
    return ProductionPlanPresenter(
        connection_provider=lambda: p.conn, session_context=sesion,
        query_factory=ProductionPlanQueryService,
        use_cases={"create": CreateProductionPlanUseCase(auth),
                   "add_line": AddProductionPlanLineUseCase(auth),
                   "remove_line": RemoveProductionPlanLineUseCase(auth),
                   "generate": GenerateProductionPlanUseCase(auth),
                   "submit": SubmitProductionPlanUseCase(auth),
                   "approve": ApproveProductionPlanUseCase(auth),
                   "cancel": CancelProductionPlanUseCase(auth),
                   "convert": ConvertProductionPlanLineUseCase(
                       auth, folio_port=ProcessingOrderFolioAdapter)},
        suggestion_sources=fuentes or {"REPLENISHMENT": ReplenishmentPlanSource},
        warehouse_provider=lambda: (p.warehouse, None))


def test_the_screen_walks_the_plan_to_an_order(planta):
    planeador, aprobador, convertidor = new_uuid(), new_uuid(), new_uuid()
    pres = _presentador(planta, planeador)
    assert pres.plan(HOY).actions == {"create"}
    assert pres.create_plan(HOY)[0]
    modelo = pres.plan(HOY)
    assert "add" in modelo.actions and "approve" not in modelo.actions
    ok, msg, _ = pres.add_line(modelo.plan_id, product_id=planta.chorizo,
                               process_type="MIXING", target_product_id=None,
                               planned_weight=Decimal("25"), planned_quantity=Decimal("0"),
                               priority=1, source_type="MANUAL", source_reference_id=None)
    assert ok, msg
    for accion in ("generate", "submit"):
        assert pres.transition(accion, modelo.plan_id)[0]
    assert _presentador(planta, aprobador).transition("approve", modelo.plan_id)[0]
    convertir = _presentador(planta, convertidor)
    modelo = convertir.plan(HOY)
    assert modelo.actions >= {"convert"}
    ok, msg, datos = convertir.convert_line(modelo.plan_id, modelo.row_ids[0])
    assert ok, msg
    fila = convertir.plan(HOY).rows[0]
    assert fila[0] == "Chorizo" and fila[5] == datos["folio"]
    assert not any(is_uuidv7(c) for c in fila)


@pytest.fixture(scope="module")
def app():
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_page_opens_and_enables_by_state(app, planta):
    from frontend.desktop.modules.meat_processing.pages.production_plan_page import (
        ProductionPlanPage,
    )
    pagina = ProductionPlanPage(_presentador(planta, new_uuid()), title="Plan de producción",
                                subtitle="")
    pagina.day.set_date_value(HOY)
    pagina.ensure_loaded()
    assert pagina.buttons["create"].isEnabled()
    assert not pagina.buttons["convert"].isEnabled()
