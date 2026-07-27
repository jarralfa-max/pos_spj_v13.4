import pytest

from core.delivery.domain.entities import DeliveryItem, DeliveryOrder
from core.delivery.domain.states import AdjustmentStatus, DeliveryStatus, DeliveryType, DeliveryWorkflowType
from core.delivery.domain.value_objects import GeoPoint, Money, Quantity


def test_order_from_mapping_normalizes_legacy_values_and_items():
    order = DeliveryOrder.from_mapping({
        "estado": "en_preparacion",
        "workflow_type": "mostrador",
        "delivery_type": "pickup",
        "items": [{"nombre": "Pollo", "cantidad": 2, "precio_unitario": 50, "adjustment_status": "pending_customer"}],
    })
    assert order.estado == DeliveryStatus.PREPARING
    assert order.workflow_type == DeliveryWorkflowType.COUNTER
    assert order.delivery_type == DeliveryType.PICKUP
    assert order.items[0].subtotal == 100.0
    assert order.has_pending_adjustment is True


def test_item_from_mapping_supports_legacy_keys():
    item = DeliveryItem.from_mapping({"product_id": 7, "name": "Ribeye", "qty": 1.2, "unit_price": 350})
    assert item.producto_id == 7
    assert item.nombre == "Ribeye"
    assert item.subtotal == 420.0
    assert item.adjustment_status == AdjustmentStatus.NONE


def test_value_objects_validate_domain_values():
    assert Money("10.005").as_float() == 10.01
    assert Quantity("2.500", "KG").unit == "kg"
    GeoPoint(19.4, -99.1)
    with pytest.raises(ValueError, match="negativa"):
        Quantity(-1)
    with pytest.raises(ValueError, match="Latitud"):
        GeoPoint(100, 0)
