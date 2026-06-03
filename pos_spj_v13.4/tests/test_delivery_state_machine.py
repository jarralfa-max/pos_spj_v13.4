import pytest

from core.delivery.domain.entities import DeliveryItem, DeliveryOrder
from core.delivery.domain.state_machine import DeliveryStateMachine
from core.delivery.domain.states import DeliveryStatus, DeliveryWorkflowType


sm = DeliveryStateMachine()


def test_normalize_legacy_statuses():
    assert sm.normalize_status("asignado") == DeliveryStatus.PREPARACION
    assert sm.normalize_status("pendiente_wa") == DeliveryStatus.PENDIENTE
    assert sm.normalize_status("entregada") == DeliveryStatus.ENTREGADO


def test_unknown_status_is_rejected_in_domain():
    with pytest.raises(ValueError, match="desconocido"):
        sm.normalize_status("inventado")


def test_infer_workflow_from_delivery_type_and_programado():
    assert sm.infer_workflow({"estado": "programado"}) == DeliveryWorkflowType.SCHEDULED
    assert sm.infer_workflow({"estado": "pendiente", "delivery_type": "pickup"}) == DeliveryWorkflowType.COUNTER
    assert sm.infer_workflow({"estado": "pendiente", "delivery_type": "domicilio"}) == DeliveryWorkflowType.DELIVERY


def test_pendiente_to_preparacion_allowed():
    sm.assert_can_transition({"estado": "pendiente", "workflow_type": "delivery"}, "preparacion")


def test_delivery_preparacion_to_en_ruta_allowed():
    sm.assert_can_transition({"estado": "preparacion", "workflow_type": "delivery"}, "en_ruta")


def test_delivery_preparacion_to_entregado_forbidden_even_with_responsable():
    with pytest.raises(ValueError, match="en_ruta"):
        sm.assert_can_transition(
            {"estado": "preparacion", "workflow_type": "delivery", "responsable_entrega": "r1"},
            "entregado",
        )


def test_counter_preparacion_to_entregado_allowed_with_responsable():
    sm.assert_can_transition(
        {"estado": "preparacion", "workflow_type": "counter", "responsable_entrega": "caja"},
        "entregado",
    )


def test_counter_to_en_ruta_forbidden():
    with pytest.raises(ValueError, match="mostrador"):
        sm.assert_can_transition({"estado": "preparacion", "workflow_type": "counter"}, "en_ruta")


def test_scheduled_cannot_prepare_without_activation():
    with pytest.raises(ValueError, match="programado"):
        sm.assert_can_transition({"estado": "programado", "workflow_type": "scheduled"}, "preparacion")


def test_delivered_requires_responsable():
    with pytest.raises(ValueError, match="responsable"):
        sm.assert_can_transition({"estado": "en_ruta", "workflow_type": "delivery"}, "entregado")


def test_pending_adjustment_blocks_route_and_delivery_from_order_items():
    order = DeliveryOrder(
        estado=DeliveryStatus.PREPARACION,
        workflow_type=DeliveryWorkflowType.DELIVERY,
        items=[DeliveryItem(adjustment_status="pending_customer")],
    )
    with pytest.raises(ValueError, match="ajuste"):
        sm.assert_can_transition(order, "en_ruta")


def test_cancelled_reactivation_can_be_disabled():
    locked_sm = DeliveryStateMachine(allow_cancelled_reactivation=False)
    with pytest.raises(ValueError, match="cancelado"):
        locked_sm.assert_can_transition({"estado": "cancelado"}, "pendiente")


def test_delivered_cannot_go_back():
    with pytest.raises(ValueError, match="reverso"):
        sm.assert_can_transition({"estado": "entregado", "workflow_type": "delivery"}, "pendiente")


def test_valid_actions_are_domain_keys_not_ui_labels():
    assert sm.get_valid_actions({"estado": "programado"}) == ["activar_programado", "reprogramar", "cancelado"]
    assert sm.get_valid_actions({"estado": "preparacion", "workflow_type": "counter"}) == [
        "ajustar_peso",
        "entregado",
        "cancelado",
    ]
