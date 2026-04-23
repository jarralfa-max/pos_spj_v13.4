from pathlib import Path


def test_transferencias_usa_eventbus_instanciado():
    src = Path('repositories/transferencias.py').read_text(encoding='utf-8')
    assert 'EventBus().publish(TRANSFER_DISPATCHED' in src
    assert 'EventBus().publish(TRANSFER_RECEIVED' in src
    assert 'EventBus().publish(TRANSFER_CANCELLED' in src


def test_ventas_usa_eventbus_instanciado():
    src = Path('repositories/ventas.py').read_text(encoding='utf-8')
    assert 'EventBus().publish(VENTA_COMPLETADA' in src
