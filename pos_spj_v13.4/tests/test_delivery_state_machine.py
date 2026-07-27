import pytest

from core.delivery.domain.entities import DeliveryItem, DeliveryOrder
from core.delivery.domain.state_machine import DeliveryStateMachine
from core.delivery.domain.states import DeliveryStatus, DeliveryWorkflowType


sm = DeliveryStateMachine()


def test_normalize_legacy_statuses():
    # Spanish compat aliases resolve to canonical English enum values
    assert sm.normalize_status("asignado") == DeliveryStatus.ASSIGNED
    assert sm.normalize_status("pendiente_wa") == DeliveryStatus.PENDING
    assert sm.normalize_status("entregada") == DeliveryStatus.DELIVERED


def test_unknown_status_is_rejected_in_domain():
    with pytest.raises(ValueError, match="desconocido"):
        sm.normalize_status("inventado")


def test_infer_workflow_from_delivery_type_and_scheduled():
    assert sm.infer_workflow({"estado": "scheduled"}) == DeliveryWorkflowType.SCHEDULED
    assert sm.infer_workflow({"estado": "pending", "delivery_type": "pickup"}) == DeliveryWorkflowType.COUNTER
    assert sm.infer_workflow({"estado": "pending", "delivery_type": "domicilio"}) == DeliveryWorkflowType.DELIVERY


def test_pending_to_preparing_allowed():
    sm.assert_can_transition({"estado": "pending", "workflow_type": "delivery"}, "preparing")


def test_delivery_preparing_to_in_transit_allowed():
    sm.assert_can_transition({"estado": "preparing", "workflow_type": "delivery"}, "in_transit")


def test_delivery_preparing_to_delivered_forbidden_even_with_responsable():
    with pytest.raises(ValueError, match="in_transit"):
        sm.assert_can_transition(
            {"estado": "preparing", "workflow_type": "delivery", "responsable_entrega": "r1"},
            "delivered",
        )


def test_counter_preparing_to_delivered_allowed_with_responsable():
    sm.assert_can_transition(
        {"estado": "preparing", "workflow_type": "counter", "responsable_entrega": "caja"},
        "delivered",
    )


def test_counter_to_in_transit_forbidden():
    with pytest.raises(ValueError, match="mostrador"):
        sm.assert_can_transition({"estado": "preparing", "workflow_type": "counter"}, "in_transit")


def test_scheduled_cannot_prepare_without_activation():
    with pytest.raises(ValueError, match="programado"):
        sm.assert_can_transition({"estado": "scheduled", "workflow_type": "scheduled"}, "preparing")


def test_delivered_requires_responsable():
    with pytest.raises(ValueError, match="responsable"):
        sm.assert_can_transition({"estado": "in_transit", "workflow_type": "delivery"}, "delivered")


def test_pending_adjustment_blocks_route_and_delivery_from_order_items():
    order = DeliveryOrder(
        estado=DeliveryStatus.PREPARING,
        workflow_type=DeliveryWorkflowType.DELIVERY,
        items=[DeliveryItem(adjustment_status="pending_customer")],
    )
    with pytest.raises(ValueError, match="ajuste"):
        sm.assert_can_transition(order, "in_transit")


def test_cancelled_reactivation_can_be_disabled():
    locked_sm = DeliveryStateMachine(allow_cancelled_reactivation=False)
    with pytest.raises(ValueError, match="cancelado"):
        locked_sm.assert_can_transition({"estado": "cancelled"}, "pending")


def test_delivered_cannot_go_back():
    with pytest.raises(ValueError, match="reverso"):
        sm.assert_can_transition({"estado": "delivered", "workflow_type": "delivery"}, "pending")


def test_valid_actions_are_domain_keys_not_ui_labels():
    assert sm.get_valid_actions({"estado": "scheduled"}) == ["activar_programado", "reprogramar", "cancelled"]
    assert sm.get_valid_actions({"estado": "preparing", "workflow_type": "counter"}) == [
        "ajustar_peso",
        "delivered",
        "cancelled",
    ]
