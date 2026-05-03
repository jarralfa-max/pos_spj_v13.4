"""
test_event_bus_aliases.py — v13.4
Verifica que los aliases y constantes nuevos existen en event_bus.py.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_merma_created_exists():
    from core.events.event_bus import MERMA_CREATED
    assert MERMA_CREATED == "MERMA_REGISTRADA"


def test_sale_completed_alias():
    from core.events.event_bus import SALE_COMPLETED, VENTA_COMPLETADA
    assert SALE_COMPLETED == VENTA_COMPLETADA


def test_stock_updated_alias():
    from core.events.event_bus import STOCK_UPDATED, AJUSTE_INVENTARIO
    assert STOCK_UPDATED == AJUSTE_INVENTARIO


def test_purchase_created_alias():
    from core.events.event_bus import PURCHASE_CREATED, COMPRA_REGISTRADA
    assert PURCHASE_CREATED == COMPRA_REGISTRADA


def test_pre_existing_aliases_unchanged():
    """Verifica que los aliases pre-existentes no fueron alterados."""
    from core.events.event_bus import (
        SALE_CREATED, VENTA_COMPLETADA,
        STOCK_LOW, STOCK_BAJO_MINIMO,
        PAYROLL_DUE,
        ALERT_CRITICAL,
    )
    assert SALE_CREATED == VENTA_COMPLETADA
    assert STOCK_LOW == STOCK_BAJO_MINIMO
    assert PAYROLL_DUE == "PAYROLL_DUE"
    assert ALERT_CRITICAL == "ALERT_CRITICAL"
