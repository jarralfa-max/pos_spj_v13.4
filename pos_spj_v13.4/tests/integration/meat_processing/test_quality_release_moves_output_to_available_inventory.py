"""§10/§11/§25 — cuando CALIDAD libera, Inventario pasa lo retenido a
disponible y Procesamiento registra la decisión (por el evento de Calidad, con
el bus real). Bloquear, reprocesar o decomisar lo deja fuera de disponible.
"""
from __future__ import annotations

import pytest

from backend.domain.meat_processing.enums import OutputQualityStatus
from backend.infrastructure.db.repositories.quality.inspection_repository import (
    InspectionRepository,
)
from tests.integration.meat_processing._quality_plant import PlantaConCalidad


@pytest.fixture()
def planta():
    q = PlantaConCalidad()
    yield q
    q.conn.close()


def test_quality_release_makes_the_output_available(planta):
    r = planta.p.decidir_calidad(planta.salida(planta.filete).id, "RELEASED",
                                 dispatch=planta.despachar)
    assert r.success, r.message
    assert planta.estados_en_inventario(planta.filete) == {"AVAILABLE": "8"}
    assert planta.lote_de(planta.filete) == "RELEASED"
    assert planta.salida(planta.filete).quality_status is OutputQualityStatus.RELEASED
    inspeccion = InspectionRepository(planta.conn).get(r.inspection_id)
    assert (inspeccion.status, inspeccion.decided_by_user_id) == ("RELEASED", planta.p.inspector)


@pytest.mark.parametrize("decision, estado_output, estado_lote", [
    ("BLOCKED", OutputQualityStatus.REJECTED, "BLOCKED"),
    ("REWORK_REQUIRED", OutputQualityStatus.REWORK_REQUIRED, "BLOCKED"),
    ("CONDEMNED", OutputQualityStatus.CONDEMNED, "REJECTED"),
])
def test_anything_but_release_keeps_it_out_of_available(planta, decision, estado_output,
                                                         estado_lote):
    r = planta.p.decidir_calidad(planta.salida(planta.filete).id, decision,
                                 motivo="Temperatura fuera de rango", dispatch=planta.despachar)
    assert r.success, r.message
    assert "AVAILABLE" not in planta.estados_en_inventario(planta.filete)
    assert planta.lote_de(planta.filete) == estado_lote
    assert planta.salida(planta.filete).quality_status is estado_output


def test_blocking_requires_a_reason(planta):
    r = planta.p.decidir_calidad(planta.salida(planta.filete).id, "BLOCKED",
                                 dispatch=planta.despachar)
    assert not r.success and r.error_code == "REASON_REQUIRED"
    assert planta.lote_de(planta.filete) == "QUARANTINED"


def test_delivering_the_decision_twice_does_not_duplicate_anything(planta):
    planta.p.decidir_calidad(planta.salida(planta.filete).id, "RELEASED",
                             dispatch=planta.despachar)
    fila = planta.conn.execute("SELECT payload_json, event_name FROM quality_outbox").fetchone()
    import json
    planta.bus.publish(fila[1], json.loads(fila[0]), strict=True)   # segunda entrega
    assert planta.estados_en_inventario(planta.filete) == {"AVAILABLE": "8"}
    assert planta.salida(planta.filete).quality_status is OutputQualityStatus.RELEASED
