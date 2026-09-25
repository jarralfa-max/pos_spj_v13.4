"""Reparto del costo conjunto de una transformación (Costos, no Procesamiento).

Movido de `tests/unit/meat_processing/test_cost_allocation_service.py` con las
mismas aserciones del valor de venta relativo (la decisión vigente del usuario)
y cobertura de los demás métodos configurables. Los productos son datos: las
mismas reglas valen para una canal, una pieza o una mezcla.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.costing.services.joint_cost_allocation import (
    AllocationInput,
    AllocationMethod,
    CostAllocationError,
    JointCostAllocator,
)


def _entrada(pid, tipo, peso, precio=None, **extra):
    return AllocationInput(product_id=pid, output_type=tipo, weight=Decimal(peso),
                           unit_price=None if precio is None else Decimal(precio), **extra)


#: Transformación de referencia: 10 kg de entrada a 50/kg = 500 de costo.
SALIDAS = [
    _entrada("principal", "MAIN_PRODUCT", "3.4", "120"),
    _entrada("coproducto-a", "CO_PRODUCT", "3.0", "80"),
    _entrada("coproducto-b", "CO_PRODUCT", "1.2", "60"),
    _entrada("merma", "WASTE", "0.5"),
]

RSV = JointCostAllocator(AllocationMethod.RELATIVE_SALES_VALUE)


class TestValorDeVentaRelativo:
    def test_reparte_todo_el_costo_sin_perder_un_centavo(self):
        assert sum(s.allocated_cost for s in RSV.allocate(Decimal("500"), SALIDAS)) == 500

    def test_cada_salida_carga_en_proporcion_a_kg_por_precio(self):
        por_id = {s.product_id: s for s in RSV.allocate(Decimal("500"), SALIDAS)}
        assert por_id["principal"].allocated_cost == Decimal("283.33")
        assert por_id["coproducto-a"].allocated_cost == Decimal("166.67")
        assert por_id["coproducto-b"].allocated_cost == Decimal("50.00")
        assert por_id["principal"].unit_cost == Decimal("83.3324")

    def test_la_merma_no_absorbe_costo(self):
        merma = [s for s in RSV.allocate(Decimal("500"), SALIDAS) if s.product_id == "merma"][0]
        assert merma.allocated_cost == Decimal("0") and merma.unit_cost == Decimal("0")

    def test_menos_rendimiento_encarece_lo_bueno(self):
        pobre = [_entrada("principal", "MAIN_PRODUCT", "2.0", "120"),
                 _entrada("merma", "WASTE", "8.0")]
        bueno = RSV.allocate(Decimal("500"), pobre)[0]
        normal = [s for s in RSV.allocate(Decimal("500"), SALIDAS)
                  if s.product_id == "principal"][0]
        assert bueno.unit_cost > normal.unit_cost

    def test_salida_buena_sin_precio_es_error_no_cero(self):
        with pytest.raises(CostAllocationError) as exc:
            RSV.allocate(Decimal("500"), [_entrada("principal", "MAIN_PRODUCT", "3.4"),
                                          _entrada("coproducto", "CO_PRODUCT", "3", "80")])
        assert "principal" in str(exc.value)

    def test_precio_cero_tambien_es_error(self):
        with pytest.raises(CostAllocationError):
            RSV.allocate(Decimal("500"), [_entrada("principal", "MAIN_PRODUCT", "3.4", "0"),
                                          _entrada("coproducto", "CO_PRODUCT", "3", "80")])


class TestOtrosMetodos:
    def test_por_peso_la_merma_si_carga_su_parte(self):
        por_id = {s.product_id: s for s in JointCostAllocator(
            AllocationMethod.WEIGHT_BASED).allocate(Decimal("500"), SALIDAS)}
        assert por_id["merma"].allocated_cost > 0
        assert sum(s.allocated_cost for s in por_id.values()) == Decimal("500")
        # mismo $/kg para todos cuando la base es el peso (salvo el centavo de redondeo)
        assert abs(por_id["principal"].unit_cost - por_id["coproducto-a"].unit_cost) < Decimal("0.01")

    def test_valor_neto_realizable_descuenta_el_costo_separable(self):
        salidas = [_entrada("a", "MAIN_PRODUCT", "1", "100", separable_unit_cost=Decimal("50")),
                   _entrada("b", "CO_PRODUCT", "1", "100")]
        por_id = {s.product_id: s for s in JointCostAllocator(
            AllocationMethod.NET_REALIZABLE_VALUE).allocate(Decimal("150"), salidas)}
        assert por_id["a"].allocated_cost == Decimal("50.00")
        assert por_id["b"].allocated_cost == Decimal("100.00")

    def test_costo_estandar_exige_el_estandar_de_cada_salida(self):
        with pytest.raises(CostAllocationError):
            JointCostAllocator(AllocationMethod.STANDARD_COST).allocate(
                Decimal("100"), [_entrada("a", "MAIN_PRODUCT", "1"),
                                 _entrada("b", "CO_PRODUCT", "1",
                                          standard_unit_cost=Decimal("10"))])
        salidas = [_entrada("a", "MAIN_PRODUCT", "1", standard_unit_cost=Decimal("30")),
                   _entrada("b", "CO_PRODUCT", "1", standard_unit_cost=Decimal("10"))]
        por_id = {s.product_id: s for s in JointCostAllocator(
            AllocationMethod.STANDARD_COST).allocate(Decimal("100"), salidas)}
        assert por_id["a"].allocated_cost == Decimal("75.00")

    def test_factor_configurado_sin_factor_es_error(self):
        with pytest.raises(CostAllocationError):
            JointCostAllocator(AllocationMethod.CONFIGURED_FACTOR).allocate(
                Decimal("100"), [_entrada("a", "MAIN_PRODUCT", "1"),
                                 _entrada("b", "CO_PRODUCT", "1", factor=Decimal("1"))])
        salidas = [_entrada("a", "MAIN_PRODUCT", "1", factor=Decimal("3")),
                   _entrada("b", "CO_PRODUCT", "1", factor=Decimal("1"))]
        por_id = {s.product_id: s for s in JointCostAllocator(
            AllocationMethod.CONFIGURED_FACTOR).allocate(Decimal("100"), salidas)}
        assert por_id["a"].allocated_cost == Decimal("75.00")


class TestUnaSolaSalidaQueCargaCosto:
    """Formular, empacar o acondicionar suelen dar UN producto: se lleva todo el
    costo con cualquier método, así que no se le exige precio, estándar ni
    factor (antes una mezcla sin precio de venta no se podía costear)."""

    @pytest.mark.parametrize("metodo", [AllocationMethod.RELATIVE_SALES_VALUE,
                                        AllocationMethod.NET_REALIZABLE_VALUE,
                                        AllocationMethod.STANDARD_COST,
                                        AllocationMethod.CONFIGURED_FACTOR])
    def test_se_lleva_todo_sin_base(self, metodo):
        salidas = [_entrada("mezcla", "MAIN_PRODUCT", "9.5"), _entrada("merma", "WASTE", "0.5")]
        por_id = {s.product_id: s for s in JointCostAllocator(metodo).allocate(
            Decimal("950"), salidas)}
        assert por_id["mezcla"].allocated_cost == Decimal("950.00")
        assert por_id["mezcla"].unit_cost == Decimal("100.0000")
        assert por_id["merma"].allocated_cost == Decimal("0")

    def test_por_peso_la_merma_sigue_cargando_su_parte(self):
        salidas = [_entrada("mezcla", "MAIN_PRODUCT", "9.5"), _entrada("merma", "WASTE", "0.5")]
        por_id = {s.product_id: s for s in JointCostAllocator(
            AllocationMethod.WEIGHT_BASED).allocate(Decimal("1000"), salidas)}
        assert por_id["merma"].allocated_cost == Decimal("50.00")


class TestFallosExplicitos:
    def test_solo_merma_no_tiene_entre_que_repartir(self):
        with pytest.raises(CostAllocationError):
            RSV.allocate(Decimal("500"), [_entrada("merma", "WASTE", "10")])

    def test_costo_negativo_se_rechaza(self):
        with pytest.raises(CostAllocationError):
            RSV.allocate(Decimal("-1"), SALIDAS)

    def test_costo_cero_reparte_cero(self):
        assert all(s.allocated_cost == 0 for s in RSV.allocate(Decimal("0"), SALIDAS))

    def test_float_se_rechaza(self):
        with pytest.raises(TypeError):
            AllocationInput(product_id="a", output_type="MAIN_PRODUCT",
                            weight=Decimal("1"), factor=1.5)
