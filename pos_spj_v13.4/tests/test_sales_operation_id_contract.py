from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sales_ui_routes_checkout_through_helper_with_operation_id() -> None:
    src = (ROOT / "modulos" / "ventas.py").read_text(encoding="utf-8")
    start = src.find("def _procesar_venta_via_uc")
    assert start >= 0
    end = src.find("\n    def ", start + 1)
    block = src[start:end if end > start else None]

    assert "_uc.ejecutar(" in block
    assert "operation_id=operation_id" in block
    assert "execute_sale(" not in block


def test_sales_completed_event_payload_includes_operation_id() -> None:
    src = (ROOT / "core" / "services" / "sales_service.py").read_text(encoding="utf-8")
    publish_pos = src.find("get_bus().publish(VENTA_COMPLETADA")
    assert publish_pos >= 0
    block = src[publish_pos: src.find("}, async_=True)", publish_pos)]

    assert '"operation_id"' in block
    assert "operation_id" in block
