from modulos.delivery import DeliveryActionPolicy


def _actions(actions):
    return {a[2] for a in actions}


def test_counter_workflow_hides_delivery_actions():
    actions = DeliveryActionPolicy.get_actions("preparacion", workflow_type="counter")
    names = _actions(actions)
    assert "en_ruta" not in names
    assert "asignar" not in names
    assert "entregado" in names


def test_delivery_workflow_keeps_route_action():
    actions = DeliveryActionPolicy.get_actions("preparacion", workflow_type="delivery")
    names = _actions(actions)
    assert "en_ruta" in names


def test_adjustment_pending_blocks_route_and_delivery():
    actions = DeliveryActionPolicy.get_actions(
        "preparacion", workflow_type="delivery", adjustment_pending=True
    )
    names = _actions(actions)
    assert "en_ruta" not in names
    assert "entregado" not in names
