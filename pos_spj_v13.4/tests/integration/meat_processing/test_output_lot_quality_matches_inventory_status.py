"""§11/§25 — el estado de calidad del OUTPUT, el del LOTE en Inventario y el
estado del SALDO siempre dicen lo mismo, en cada momento del ciclo."""
from __future__ import annotations

import pytest

from backend.domain.meat_processing.enums import OutputQualityStatus
from tests.integration.meat_processing._quality_plant import PlantaConCalidad

#: output → (lote, estado del saldo)
COHERENTE = {
    OutputQualityStatus.NOT_REQUIRED: ("RELEASED", "AVAILABLE"),
    OutputQualityStatus.QUARANTINED: ("QUARANTINED", "QUARANTINED"),
    OutputQualityStatus.RELEASED: ("RELEASED", "AVAILABLE"),
    OutputQualityStatus.REJECTED: ("BLOCKED", "QUALITY_BLOCKED"),
    OutputQualityStatus.REWORK_REQUIRED: ("BLOCKED", "QUALITY_BLOCKED"),
    OutputQualityStatus.CONDEMNED: ("REJECTED", "QUALITY_BLOCKED"),
}


def _coherente(planta, producto):
    salida = planta.salida(producto)
    lote, saldo = COHERENTE[salida.quality_status]
    assert planta.lote_de(producto) == lote
    assert set(planta.estados_en_inventario(producto)) == {saldo}


@pytest.fixture()
def planta():
    q = PlantaConCalidad()
    yield q
    q.conn.close()


def test_right_after_execution(planta):
    _coherente(planta, planta.filete)
    _coherente(planta, planta.cabeza)


@pytest.mark.parametrize("decision", ["RELEASED", "BLOCKED", "REWORK_REQUIRED", "CONDEMNED"])
def test_after_each_quality_decision(planta, decision):
    assert planta.p.decidir_calidad(planta.salida(planta.filete).id, decision,
                                    motivo="revisión", dispatch=planta.despachar).success
    _coherente(planta, planta.filete)
