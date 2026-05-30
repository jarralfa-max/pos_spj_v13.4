from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from core.events.domain_events import SALE_ITEMS_PROCESS
from core.events.event_bus import EventBus
from core.services.sales_service import SalesService


class _Bus:
    def __init__(self, labels):
        self._labels = labels

    def handler_labels(self, _event_type):
        return list(self._labels)


def _svc():
    return SalesService.__new__(SalesService)


def test_sale_fails_without_inventory_handler():
    with pytest.raises(RuntimeError, match="inventario"):
        _svc()._validate_critical_sale_handlers(
            _Bus(["sale_finance_income"]),
            SALE_ITEMS_PROCESS,
            "Efectivo",
        )


def test_sale_fails_without_finance_handler():
    with pytest.raises(RuntimeError, match="finanzas/caja"):
        _svc()._validate_critical_sale_handlers(
            _Bus(["sale_inventory_deduct"]),
            SALE_ITEMS_PROCESS,
            "Efectivo",
        )


def test_credit_sale_fails_without_credit_handler():
    with pytest.raises(RuntimeError, match="crédito"):
        _svc()._validate_critical_sale_handlers(
            _Bus(["sale_inventory_deduct", "sale_finance_income"]),
            SALE_ITEMS_PROCESS,
            "Credito",
        )




def test_sale_all_critical_handlers_registered_passes():
    _svc()._validate_critical_sale_handlers(
        _Bus([
            "sale_inventory_deduct",
            "sale_finance_income",
            "sale_credit_cxc",
        ]),
        SALE_ITEMS_PROCESS,
        "Credito",
    )

def test_sale_items_process_not_noop_in_production():
    bus = object.__new__(EventBus)
    bus._handlers = {}
    bus._lock = threading.RLock()
    bus._executor = ThreadPoolExecutor(max_workers=1)
    try:
        with pytest.raises(RuntimeError, match="Handlers críticos"):
            bus.publish(SALE_ITEMS_PROCESS, {"sale_id": 1}, strict=True)
    finally:
        bus._executor.shutdown(wait=False)
