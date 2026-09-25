"""Plan de producción (decisiones del usuario, 2026-09-25): un plan por
sucursal y día; líneas manuales o sugeridas; lo aprueba otro usuario; convertir
una línea crea la orden APROBADA (con folio) y la deja lista para preparar."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

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
from backend.domain.meat_processing.enums import (
    ProcessingOrderStatus,
    ProcessType,
    ProductionPlanStatus,
)
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.integrations.meat_processing_ports import (
    ProcessingOrderFolioAdapter,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import Planta, build_db

HOY = date(2026, 9, 25)


@pytest.fixture()
def planta():
    conn = build_db()
    p = Planta(conn)
    p.planeador, p.aprobador, p.convertidor = new_uuid(), new_uuid(), new_uuid()
    especie = p.especie("Porcino")
    p.lomo = p.producto("Lomo de cerdo entero", especie=especie)
    p.chuleta = p.producto("Chuleta", especie=especie)
    p.despiece(p.lomo, [(p.chuleta, "MAIN_PRODUCT", "1")], especie=especie)
    p.existencia(p.lomo, "100")
    yield p
    conn.close()


def _plan(p):
    r = CreateProductionPlanUseCase(p.auth()).execute(
        p.conn, branch_id=p.branch, planning_date=HOY, operation_id=new_uuid(),
        actor_user_id=p.planeador)
    assert r.success, r.message
    return r.entity_id


def _linea(p, plan_id, peso="30"):
    r = AddProductionPlanLineUseCase(p.auth()).execute(
        p.conn, plan_id=plan_id, product_id=p.chuleta, process_type=ProcessType.CUTTING,
        target_product_id=p.lomo, planned_weight=Decimal(peso), operation_id=new_uuid(),
        actor_user_id=p.planeador)
    assert r.success, r.message
    return r.entity_id


def _aprobado(p, plan_id):
    for caso, quien in ((GenerateProductionPlanUseCase, p.planeador),
                        (SubmitProductionPlanUseCase, p.planeador),
                        (ApproveProductionPlanUseCase, p.aprobador)):
        r = caso(p.auth()).execute(p.conn, plan_id=plan_id, operation_id=new_uuid(),
                                   actor_user_id=quien)
        assert r.success, r.message


def _convertir(p, plan_id, linea_id, *, quien=None, peso=None, op=None):
    return ConvertProductionPlanLineUseCase(
        p.auth(), folio_port=ProcessingOrderFolioAdapter).execute(
        p.conn, plan_id=plan_id, line_id=linea_id, warehouse_id=p.warehouse,
        operation_id=op or new_uuid(), actor_user_id=quien or p.convertidor,
        planned_weight=peso)


def _plan_de(p, plan_id):
    return MeatProcessingUnitOfWork(p.conn).production_plans.get(plan_id)


def test_one_plan_per_branch_and_day(planta):
    primero = _plan(planta)
    otra_vez = CreateProductionPlanUseCase(planta.auth()).execute(
        planta.conn, branch_id=planta.branch, planning_date="2026-09-25",
        operation_id=new_uuid(), actor_user_id=planta.planeador)
    assert otra_vez.success and otra_vez.entity_id == primero
    assert otra_vez.data["already_processed"] is True
    assert _plan_de(planta, primero).planning_period == "2026-09-25"


def test_an_invalid_day_is_refused(planta):
    r = CreateProductionPlanUseCase(planta.auth()).execute(
        planta.conn, branch_id=planta.branch, planning_date="semana 39",
        operation_id=new_uuid(), actor_user_id=planta.planeador)
    assert not r.success and r.error_code == "INVALID_PLANNING_DATE"


def test_the_full_flow_ends_in_an_approved_order_with_folio(planta):
    plan_id = _plan(planta)
    linea = _linea(planta, plan_id)
    _aprobado(planta, plan_id)

    r = _convertir(planta, plan_id, linea)

    assert r.success, r.message
    orden = MeatProcessingUnitOfWork(planta.conn).orders.get(r.entity_id)
    assert orden.status is ProcessingOrderStatus.APPROVED
    assert orden.approved_by_user_id == planta.aprobador
    assert orden.created_by_user_id == planta.convertidor
    assert orden.folio == f"OP-{planta.codigo}-00001"
    assert (orden.process_type, orden.target_product_id, orden.planned_weight) == (
        ProcessType.CUTTING, planta.lomo, Decimal("30"))
    assert (orden.source_type, orden.source_reference_id) == ("PRODUCTION_PLAN", linea)
    assert _plan_de(planta, plan_id).status is ProductionPlanStatus.CONVERTED
    # Nace aprobada: se prepara (reserva) como cualquier otra.
    assert planta.preparar(orden.id).data["ready"] is True


def test_whoever_approved_the_plan_does_not_convert_it(planta):
    plan_id = _plan(planta)
    linea = _linea(planta, plan_id)
    _aprobado(planta, plan_id)
    r = _convertir(planta, plan_id, linea, quien=planta.aprobador)
    assert not r.success and r.error_code == "SEGREGATION_OF_DUTIES"
    assert planta.conn.execute("SELECT COUNT(*) FROM processing_orders").fetchone()[0] == 0


def test_the_creator_cannot_approve_the_plan(planta):
    plan_id = _plan(planta)
    _linea(planta, plan_id)
    for caso in (GenerateProductionPlanUseCase, SubmitProductionPlanUseCase):
        caso(planta.auth()).execute(planta.conn, plan_id=plan_id, operation_id=new_uuid(),
                                    actor_user_id=planta.planeador)
    r = ApproveProductionPlanUseCase(planta.auth()).execute(
        planta.conn, plan_id=plan_id, operation_id=new_uuid(), actor_user_id=planta.planeador)
    assert not r.success
    assert _plan_de(planta, plan_id).status is ProductionPlanStatus.UNDER_REVIEW


def test_an_unapproved_plan_is_not_converted(planta):
    plan_id = _plan(planta)
    linea = _linea(planta, plan_id)
    r = _convertir(planta, plan_id, linea)
    assert not r.success and r.error_code == "PLAN_NOT_APPROVED"


def test_partial_conversion_and_no_duplicates_on_retry(planta):
    plan_id = _plan(planta)
    linea = _linea(planta, plan_id, peso="30")
    _aprobado(planta, plan_id)
    op = new_uuid()
    primera = _convertir(planta, plan_id, linea, peso="10", op=op)
    otra_vez = _convertir(planta, plan_id, linea, peso="10", op=op)      # reintento
    assert primera.success and otra_vez.success
    assert otra_vez.entity_id == primera.entity_id
    plan = _plan_de(planta, plan_id)
    assert plan.status is ProductionPlanStatus.PARTIALLY_CONVERTED
    assert plan.lines[0].converted_weight == Decimal("10")
    resto = _convertir(planta, plan_id, linea)                           # lo que falta
    assert resto.success
    assert MeatProcessingUnitOfWork(planta.conn).orders.get(resto.entity_id).planned_weight \
        == Decimal("20")
    assert _plan_de(planta, plan_id).status is ProductionPlanStatus.CONVERTED
    assert not _convertir(planta, plan_id, linea).success               # nada que convertir


def test_converting_more_than_planned_is_refused(planta):
    plan_id = _plan(planta)
    linea = _linea(planta, plan_id, peso="30")
    _aprobado(planta, plan_id)
    r = _convertir(planta, plan_id, linea, peso="40")
    assert not r.success


def test_lines_are_edited_only_before_review_and_a_plan_can_be_cancelled(planta):
    plan_id = _plan(planta)
    linea = _linea(planta, plan_id)
    assert RemoveProductionPlanLineUseCase(planta.auth()).execute(
        planta.conn, plan_id=plan_id, line_id=linea, operation_id=new_uuid(),
        actor_user_id=planta.planeador).success
    assert _plan_de(planta, plan_id).lines == []
    assert CancelProductionPlanUseCase(planta.auth()).execute(
        planta.conn, plan_id=plan_id, operation_id=new_uuid(),
        actor_user_id=planta.planeador).success
    assert _plan_de(planta, plan_id).status is ProductionPlanStatus.CANCELLED


def test_a_formulation_line_targets_what_it_makes(planta):
    res, mezcla = planta.producto("Res"), planta.producto("Mezcla")
    plan_id = _plan(planta)
    r = AddProductionPlanLineUseCase(planta.auth()).execute(
        planta.conn, plan_id=plan_id, product_id=mezcla, process_type="MIXING",
        target_product_id=None, planned_weight=Decimal("15"), operation_id=new_uuid(),
        actor_user_id=planta.planeador)
    assert r.success
    assert _plan_de(planta, plan_id).lines[0].target_product_id == mezcla
    del res
