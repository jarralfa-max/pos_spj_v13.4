from core.services.sales_reversal_service import SalesReversalService


def test_phase10_event_names_present_for_compensations():
    import inspect
    src = inspect.getsource(SalesReversalService)
    assert 'SALE_CANCELLED' in src
    assert 'SALE_REFUNDED' in src
    assert 'SALE_CREDIT_NOTE_ISSUED' in src
    assert 'SALE_LOYALTY_REVERSED' in src
    assert 'SALE_CASH_COMPENSATED' in src
    assert 'SALE_INVENTORY_RESTORED' in src
