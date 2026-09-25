"""§4/§25 — empacar exige una ESPECIFICACIÓN DE EMPAQUE (receta de empaque o
perfil logístico), nunca un esquema de corte ni una receta de producción.

Filete de pescado: se empaca sin tener despiece. El comportamiento sale de la
familia del proceso (empaque = identidad: lo que entra, sale empacado).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
    MasterDataKind,
)
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


@pytest.mark.parametrize("proceso", [ProcessType.PACKAGING, ProcessType.REPACKAGING,
                                     ProcessType.LABELING])
def test_packaging_prepares_with_a_packaging_spec_and_no_cutting_scheme(planta, proceso):
    filete = planta.producto("Filete de pescado", lote=True)
    charola = planta.producto("Charola con película")
    planta.receta(filete, [(charola, "1")], tipo="PACKAGING_BOM")
    planta.existencia(filete, "30", lote="FIL-1", vence="2031-02-01")

    oid = planta.lista(proceso, filete, "12")

    foto = MeatProcessingUnitOfWork(planta.conn).recipe_snapshots.get_by_order(oid)
    assert foto.cutting_scheme_version_id is None
    assert MasterDataKind.PACKAGING_SPEC in foto.present_master_data
    assert foto.packaging_spec["source"] == "PACKAGING_BOM"
    assert [i.product_id for i in foto.inputs] == [filete]
    assert [o.product_id for o in foto.outputs] == [filete]
    assert planta.reservado(filete) == Decimal("12")


def test_packaging_without_any_packaging_spec_is_not_prepared(planta):
    filete = planta.producto("Filete de pescado")
    planta.existencia(filete, "30")

    oid = planta.orden(ProcessType.PACKAGING, filete, "12")
    r = planta.preparar(oid)

    assert not r.success and r.error_code == "MASTER_DATA_MISSING"
    assert MeatProcessingUnitOfWork(planta.conn).orders.get(oid).status is \
        ProcessingOrderStatus.APPROVED
    assert planta.reservado(filete) == Decimal("0")


def test_packaging_executes_as_identity_and_keeps_the_lot_genealogy(planta):
    filete = planta.producto("Filete de pescado", lote=True)
    charola = planta.producto("Charola con película")
    planta.receta(filete, [(charola, "1")], tipo="PACKAGING_BOM")
    planta.costo(filete, "140")
    lote = planta.existencia(filete, "30", lote="FIL-1", vence="2031-02-01")

    oid = planta.lista(ProcessType.PACKAGING, filete, "12")
    r = planta.ejecutar(oid, {filete: "12"})

    assert r.success, r.message
    resultado = r.data["results"][0]
    assert resultado["input_lot_id"] == lote
    assert resultado["output_lot_id"] and resultado["output_lot_id"] != lote
    assert planta.saldo(filete) == Decimal("30")      # 18 del lote original + 12 empacados
