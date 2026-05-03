# tests/test_fase4_stock_validation.py
# Fase 4 — Validación de stock en ProcesarVentaUC
# Verifica que _validar_stock() bloquea ventas con stock insuficiente
# y omite la validación para productos compuestos (combos).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock
from core.use_cases.venta import ProcesarVentaUC, ItemCarrito


def _make_uc(stock_por_producto: dict) -> ProcesarVentaUC:
    """Crea un ProcesarVentaUC con inventory_service mock."""
    inv = MagicMock()
    inv.get_stock.side_effect = lambda pid, sid: stock_por_producto.get(pid, 0.0)
    return ProcesarVentaUC(
        sales_service=MagicMock(),
        inventory_service=inv,
        finance_service=MagicMock(),
        loyalty_service=MagicMock(),
        ticket_engine=MagicMock(),
    )


# ── Validación positiva (stock suficiente) ────────────────────────────────────

def test_stock_suficiente_retorna_none():
    """Con stock suficiente, _validar_stock() debe retornar None."""
    uc = _make_uc({1: 10.0})
    items = [ItemCarrito(producto_id=1, cantidad=5.0, precio_unit=100.0, nombre="Pollo")]
    assert uc._validar_stock(items, sucursal_id=1) is None


def test_stock_exacto_pasa():
    """Stock == cantidad pedida debe pasar la validación."""
    uc = _make_uc({1: 5.0})
    items = [ItemCarrito(producto_id=1, cantidad=5.0, precio_unit=100.0, nombre="Agua")]
    assert uc._validar_stock(items, sucursal_id=1) is None


def test_multiples_items_todos_suficientes():
    """Todos los ítems con stock suficiente deben retornar None."""
    uc = _make_uc({1: 10.0, 2: 20.0})
    items = [
        ItemCarrito(producto_id=1, cantidad=3.0, precio_unit=50.0),
        ItemCarrito(producto_id=2, cantidad=5.0, precio_unit=30.0),
    ]
    assert uc._validar_stock(items, sucursal_id=1) is None


# ── Validación negativa (stock insuficiente) ─────────────────────────────────

def test_stock_insuficiente_retorna_mensaje_error():
    """Con stock insuficiente, debe retornar un mensaje de error (str)."""
    uc = _make_uc({1: 3.0})
    items = [ItemCarrito(producto_id=1, cantidad=7.0, precio_unit=100.0, nombre="Pollo")]
    result = uc._validar_stock(items, sucursal_id=1)
    assert result is not None
    assert isinstance(result, str)


def test_mensaje_error_contiene_nombre_producto():
    """El mensaje de error debe mencionar el nombre del producto afectado."""
    uc = _make_uc({1: 2.0})
    items = [ItemCarrito(producto_id=1, cantidad=5.0, precio_unit=100.0, nombre="Pechuga")]
    result = uc._validar_stock(items, sucursal_id=1)
    assert "Pechuga" in result


def test_stock_cero_bloquea_venta():
    """Stock = 0 debe retornar mensaje de error."""
    uc = _make_uc({1: 0.0})
    items = [ItemCarrito(producto_id=1, cantidad=1.0, precio_unit=50.0, nombre="Agua 500ml")]
    assert uc._validar_stock(items, sucursal_id=1) is not None


def test_multiples_items_uno_falla():
    """Si un ítem falla, _validar_stock retorna el primer mensaje de error."""
    uc = _make_uc({1: 10.0, 2: 1.0})
    items = [
        ItemCarrito(producto_id=1, cantidad=5.0, precio_unit=50.0, nombre="OK"),
        ItemCarrito(producto_id=2, cantidad=5.0, precio_unit=30.0, nombre="Faltante"),
    ]
    result = uc._validar_stock(items, sucursal_id=1)
    assert result is not None
    assert "Faltante" in result


# ── Combos (es_compuesto=1) ────────────────────────────────────────────────────

def test_combo_omite_validacion_de_stock():
    """Productos compuestos (combos) no se validan en _validar_stock."""
    uc = _make_uc({1: 0.0})  # Stock 0, pero es combo
    items = [ItemCarrito(producto_id=1, cantidad=5.0, precio_unit=150.0,
                         nombre="Combo Familiar", es_compuesto=1)]
    assert uc._validar_stock(items, sucursal_id=1) is None


def test_mezcla_combo_y_normal_valida_solo_normal():
    """Solo los ítems normales se validan; combos siempre pasan."""
    uc = _make_uc({1: 0.0, 2: 10.0})
    items = [
        ItemCarrito(producto_id=1, cantidad=2.0, precio_unit=100.0,
                    nombre="Combo", es_compuesto=1),       # stock 0, pero combo → OK
        ItemCarrito(producto_id=2, cantidad=5.0, precio_unit=50.0,
                    nombre="Refresco", es_compuesto=0),    # stock 10 → OK
    ]
    assert uc._validar_stock(items, sucursal_id=1) is None


# ── ItemCarrito: subtotal ─────────────────────────────────────────────────────

def test_item_subtotal_sin_descuento():
    item = ItemCarrito(producto_id=1, cantidad=3.0, precio_unit=50.0)
    assert item.subtotal == 150.0


def test_item_subtotal_con_descuento():
    item = ItemCarrito(producto_id=1, cantidad=2.0, precio_unit=100.0, descuento=20.0)
    assert item.subtotal == 180.0


def test_item_subtotal_descuento_total():
    item = ItemCarrito(producto_id=1, cantidad=1.0, precio_unit=100.0, descuento=100.0)
    assert item.subtotal == 0.0
