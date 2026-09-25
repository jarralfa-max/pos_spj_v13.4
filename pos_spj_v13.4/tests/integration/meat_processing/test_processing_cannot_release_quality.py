"""§10/§25 — Procesamiento no libera calidad. Lo sujeto a inspección entra
retenido y así se queda hasta que CALIDAD decide, con segregación de funciones.
"""
from __future__ import annotations

import pytest

from backend.application.meat_processing.use_cases import RecordQualityDecisionUseCase
from backend.application.quality.output_inspection import (
    DecideOutputInspectionUseCase,
    QualityAuthorizationPolicy,
)
from backend.application.quality.permissions import QualityPermissions
from backend.domain.meat_processing.enums import OutputQualityStatus, ProcessingOrderStatus
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.db.repositories.quality.inspection_repository import (
    InspectionRepository,
)
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import _Only
from tests.integration.meat_processing._quality_plant import PlantaConCalidad


@pytest.fixture()
def planta():
    q = PlantaConCalidad()
    yield q
    q.conn.close()


def test_closing_the_order_does_not_release_what_needs_inspection(planta):
    assert MeatProcessingUnitOfWork(planta.conn).orders.get(planta.oid).status is \
        ProcessingOrderStatus.CLOSED
    assert planta.salida(planta.filete).quality_status is OutputQualityStatus.QUARANTINED
    assert planta.lote_de(planta.filete) == "QUARANTINED"
    assert planta.estados_en_inventario(planta.filete) == {"QUARANTINED": "8"}
    inspeccion = InspectionRepository(planta.conn).find_by_subject(
        "PROCESS_OUTPUT", planta.salida(planta.filete).id)
    assert inspeccion.status == "PENDING"


def test_processing_cannot_record_a_release_that_quality_did_not_decide(planta):
    salida = planta.salida(planta.filete)
    r = RecordQualityDecisionUseCase().execute(
        planta.conn, output_id=salida.id, operation_id=new_uuid(),
        decision=OutputQualityStatus.RELEASED, actor_user_id=planta.p.gerente,
        quality_inspection_id=InspectionRepository(planta.conn).find_by_subject(
            "PROCESS_OUTPUT", salida.id).id)
    assert not r.success and r.error_code == "QUALITY_DECISION_NOT_FOUND"
    assert planta.lote_de(planta.filete) == "QUARANTINED"


def test_a_production_user_without_the_quality_permission_cannot_decide(planta):
    r = planta.p.decidir_calidad(planta.salida(planta.filete).id, "RELEASED",
                                 quien=planta.p.operario)
    assert not r.success and r.error_code == "PERMISSION_DENIED"
    assert planta.lote_de(planta.filete) == "QUARANTINED"


def test_who_produced_never_decides_even_holding_the_permission(planta):
    operario = planta.p.operario
    salida = planta.salida(planta.filete)
    inspeccion = InspectionRepository(planta.conn).find_by_subject("PROCESS_OUTPUT", salida.id)
    politica = QualityAuthorizationPolicy(_Only({operario: (
        QualityPermissions.INSPECTION_DECIDE,)}))
    r = DecideOutputInspectionUseCase(politica).execute(
        planta.conn, inspection_id=inspeccion.id, decision="RELEASED", reason="",
        operation_id=new_uuid(), actor_user_id=operario)
    assert not r.success and r.error_code == "SEGREGATION_OF_DUTIES"
    assert planta.lote_de(planta.filete) == "QUARANTINED"


def test_an_output_without_inspection_requirement_is_not_held(planta):
    assert planta.salida(planta.cabeza).quality_status is OutputQualityStatus.NOT_REQUIRED
    assert planta.estados_en_inventario(planta.cabeza) == {"AVAILABLE": "4"}
    assert InspectionRepository(planta.conn).find_by_subject(
        "PROCESS_OUTPUT", planta.salida(planta.cabeza).id) is None
