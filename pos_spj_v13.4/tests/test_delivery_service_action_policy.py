from core.services.delivery_service import DeliveryService


class _DummyRepo:
    def __init__(self):
        pass


def _service():
    return DeliveryService(db=None, repository=_DummyRepo(), whatsapp_service=None, geocoding_service=None)


def _keys(actions):
    return [a.get("key") for a in actions]


def test_counter_preparacion_excludes_route_and_assign():
    svc = _service()
    actions = svc.get_valid_actions(status="preparacion", workflow_type="counter")
    keys = _keys(actions)
    assert "en_ruta" not in keys
    assert "asignar" not in keys
    assert "entregado" in keys


def test_delivery_preparacion_includes_route_and_assign():
    svc = _service()
    actions = svc.get_valid_actions(status="preparacion", workflow_type="delivery")
    keys = _keys(actions)
    assert "en_ruta" in keys
    assert "asignar" in keys


def test_scheduled_programado_actions():
    svc = _service()
    actions = svc.get_valid_actions(status="programado", workflow_type="scheduled")
    assert _keys(actions) == ["activar_programado", "reprogramar", "ver_forecast", "cancelado"]


def test_adjustment_pending_blocks_route_and_delivery():
    svc = _service()
    actions = svc.get_valid_actions(
        status="preparacion",
        workflow_type="delivery",
        adjustment_pending=True,
    )
    keys = _keys(actions)
    assert "en_ruta" not in keys
    assert "entregado" not in keys
