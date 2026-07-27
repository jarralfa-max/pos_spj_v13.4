import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
from core.domain.order_models import OrderStatus
from core.mappers.order_mapper import legacy_sale_to_whatsapp_order
from core.mappers.status_mapper import to_domain_status, to_legacy_status
from whatsapp_service.erp.mappers import normalize_whatsapp_payload


def test_status_mapping_compatibility():
    assert to_legacy_status(OrderStatus.PENDING) == "pendiente"
    assert to_domain_status("pendiente_wa") == OrderStatus.PENDING
    assert to_domain_status("en_preparacion") == OrderStatus.PREPARATION


def test_legacy_sale_to_domain_order():
    order = legacy_sale_to_whatsapp_order(
        {
            "id": 10,
            "sucursal_id": 2,
            "cliente_id": 3,
            "cliente_nombre": "Cliente",
            "cliente_tel": "555",
            "tipo_entrega": "sucursal",
            "estado": "pendiente",
        },
        items=[{"producto_id": 7, "nombre": "Pollo", "cantidad": 2, "precio_unitario": 100, "subtotal": 200}],
    )
    assert order.branch_id == 2
    assert order.customer_id == 3
    assert order.items[0].quantity == 2
    assert order.status == OrderStatus.PENDING


def test_whatsapp_payload_normalization():
    payload = normalize_whatsapp_payload({"cliente_telefono": "52155", "cliente": "Ana", "sucursal_id": 1})
    assert payload["customer_phone"] == "52155"
    assert payload["customer_name"] == "Ana"
    assert payload["branch_id"] == 1
