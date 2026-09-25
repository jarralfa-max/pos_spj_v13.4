"""§4/§25 — una formulación exige la RECETA/BOM activa del producto a fabricar,
y reserva CADA componente por lo que la receta pide.

Producto marinado: carne + marinada. Sin receta no se prepara; con receta, se
reserva cada insumo en proporción.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.processing_recipe_snapshot import InputRole
from backend.domain.meat_processing.enums import ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from tests.integration.meat_processing._generic_plant import Planta, build_db


@pytest.fixture()
def planta():
    conn = build_db()
    yield Planta(conn)
    conn.close()


@pytest.mark.parametrize("proceso", [ProcessType.MARINATION, ProcessType.MIXING,
                                     ProcessType.GRINDING, ProcessType.FORMULATION])
def test_without_recipe_the_formulation_is_not_prepared(planta, proceso):
    marinado = planta.producto("Arrachera marinada")
    arrachera = planta.producto("Arrachera")
    planta.despiece(marinado, [(arrachera, "MAIN_PRODUCT", "1")],
                    especie=planta.especie("Bovino"))  # un despiece no es receta
    planta.existencia(arrachera, "20")

    oid = planta.orden(proceso, marinado, "10")
    r = planta.preparar(oid)

    assert not r.success and r.error_code == "MASTER_DATA_MISSING"
    assert planta.reservado(arrachera) == Decimal("0")


def test_with_recipe_each_component_is_reserved_in_proportion(planta):
    marinado = planta.producto("Arrachera marinada", lote=True)
    arrachera = planta.producto("Arrachera", lote=True)
    marinada = planta.producto("Marinada")
    planta.receta(marinado, [(arrachera, "0.9"), (marinada, "0.1")], tipo="MARINATION")
    planta.existencia(arrachera, "50", lote="ARR-1"); planta.existencia(marinada, "5")

    oid = planta.lista(ProcessType.MARINATION, marinado, "20")

    assert planta.reservado(arrachera) == Decimal("18")
    assert planta.reservado(marinada) == Decimal("2")
    foto = MeatProcessingUnitOfWork(planta.conn).recipe_snapshots.get_by_order(oid)
    assert {i.role for i in foto.inputs} == {InputRole.COMPONENT}
    assert [o.product_id for o in foto.outputs] == [marinado]
