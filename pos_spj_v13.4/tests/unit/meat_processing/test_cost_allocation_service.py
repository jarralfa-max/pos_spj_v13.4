"""Reparto del costo de la entrada entre las salidas (Fase 10, §10/§13).

Decisión del usuario: valor de venta relativo. Lo que se fija aquí es que la
merma no absorbe costo, que el total repartido cuadra EXACTO con el costo de
la entrada, y que una salida buena sin precio es un error explícito y no un
cero silencioso (§18: el costo nunca se inventa).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.meat_processing.services.cost_allocation_service import (
    AllocationInput,
    CostAllocationError,
    RelativeSalesValueCostAllocation,
)


def _entrada(pid, tipo, peso, precio):
    return AllocationInput(product_id=pid, output_type=tipo, weight=Decimal(peso),
                           unit_price=None if precio is None else Decimal(precio))


#: El despiece de referencia: 10 kg de pollo a 50/kg = 500 de costo.
SALIDAS = [
    _entrada("pechuga", "MAIN_PRODUCT", "3.4", "120"),
    _entrada("pierna", "CO_PRODUCT", "3.0", "80"),
    _entrada("ala", "CO_PRODUCT", "1.2", "60"),
    _entrada("merma", "WASTE", "0.5", None),
]


class TestRepartoPorValorDeVenta:
    def test_reparte_todo_el_costo_sin_perder_un_centavo(self):
        salidas = RelativeSalesValueCostAllocation().allocate(Decimal("500"), SALIDAS)
        assert sum(s.allocated_cost for s in salidas) == Decimal("500")

    def test_cada_salida_carga_en_proporcion_a_kg_por_precio(self):
        por_id = {s.product_id: s for s in
                  RelativeSalesValueCostAllocation().allocate(Decimal("500"), SALIDAS)}
        # valor: pechuga 408, pierna 240, ala 72 → 720 en total
        assert por_id["pechuga"].allocated_cost == Decimal("283.33")
        assert por_id["pierna"].allocated_cost == Decimal("166.67")
        assert por_id["ala"].allocated_cost == Decimal("50.00")
        # y el $/kg sale del costo repartido, no del precio de venta
        assert por_id["pechuga"].unit_cost == Decimal("83.3324")

    def test_la_merma_no_absorbe_costo(self):
        merma = [s for s in RelativeSalesValueCostAllocation().allocate(
            Decimal("500"), SALIDAS) if s.product_id == "merma"][0]
        assert merma.allocated_cost == Decimal("0")
        assert merma.unit_cost == Decimal("0")

    def test_menos_rendimiento_encarece_lo_bueno(self):
        """Lo que hace útil el reparto: si sale menos producto bueno del mismo
        pollo, el $/kg de lo bueno SUBE."""
        pobre = [_entrada("pechuga", "MAIN_PRODUCT", "2.0", "120"),
                 _entrada("merma", "WASTE", "8.0", None)]
        bueno = RelativeSalesValueCostAllocation().allocate(Decimal("500"), pobre)[0]
        normal = [s for s in RelativeSalesValueCostAllocation().allocate(
            Decimal("500"), SALIDAS) if s.product_id == "pechuga"][0]
        assert bueno.unit_cost > normal.unit_cost


class TestFallosExplicitos:
    def test_salida_buena_sin_precio_es_error_no_cero(self):
        with pytest.raises(CostAllocationError) as exc:
            RelativeSalesValueCostAllocation().allocate(
                Decimal("500"), [_entrada("pechuga", "MAIN_PRODUCT", "3.4", None)])
        assert "pechuga" in str(exc.value)

    def test_precio_cero_tambien_es_error(self):
        with pytest.raises(CostAllocationError):
            RelativeSalesValueCostAllocation().allocate(
                Decimal("500"), [_entrada("pechuga", "MAIN_PRODUCT", "3.4", "0")])

    def test_solo_merma_no_tiene_entre_que_repartir(self):
        with pytest.raises(CostAllocationError):
            RelativeSalesValueCostAllocation().allocate(
                Decimal("500"), [_entrada("merma", "WASTE", "10", None)])

    def test_costo_negativo_se_rechaza(self):
        with pytest.raises(CostAllocationError):
            RelativeSalesValueCostAllocation().allocate(Decimal("-1"), SALIDAS)

    def test_costo_cero_reparte_cero(self):
        salidas = RelativeSalesValueCostAllocation().allocate(Decimal("0"), SALIDAS)
        assert all(s.allocated_cost == Decimal("0") for s in salidas)
