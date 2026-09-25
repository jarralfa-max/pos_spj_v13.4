"""§4/§25 — un despiece exige ESQUEMA DE CORTE de su entrada. Sin él la orden
no se prepara (no se reserva nada) y, por lo tanto, no se libera.

Lomo de cerdo entero: tener sólo una receta de producción, o sólo un perfil de
rendimiento, no basta para despiezar.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def planta():
    conn = build_db()
    yield Planta(conn)
    conn.close()


@pytest.mark.parametrize("proceso", [ProcessType.CUTTING, ProcessType.DISASSEMBLY,
                                     ProcessType.DEBONING, ProcessType.PORTIONING])
def test_without_cutting_scheme_the_order_is_not_prepared(planta, proceso):
    lomo = planta.producto("Lomo de cerdo entero")
    chuleta = planta.producto("Chuleta")
    planta.receta(lomo, [(chuleta, "1")])          # una receta NO es un despiece
    planta.existencia(lomo, "40")

    oid = planta.orden(proceso, lomo, "10")
    r = planta.preparar(oid)

    assert not r.success and r.error_code == "MASTER_DATA_MISSING"
    assert planta.reservado(lomo) == Decimal("0")
    uow = MeatProcessingUnitOfWork(planta.conn)
    assert uow.orders.get(oid).status is ProcessingOrderStatus.APPROVED
    assert uow.recipe_snapshots.get_by_order(oid) is None
    assert not planta.liberar(oid).success


def test_with_cutting_scheme_the_same_order_is_prepared_and_released(planta):
    lomo = planta.producto("Lomo de cerdo entero")
    chuleta = planta.producto("Chuleta")
    planta.despiece(lomo, [(chuleta, "MAIN_PRODUCT", "1")], especie=planta.especie("Porcino"))
    planta.existencia(lomo, "40")

    oid = planta.lista(ProcessType.CUTTING, lomo, "10")

    assert planta.reservado(lomo) == Decimal("10")
    assert MeatProcessingUnitOfWork(planta.conn).orders.get(oid).status is \
        ProcessingOrderStatus.RELEASED
