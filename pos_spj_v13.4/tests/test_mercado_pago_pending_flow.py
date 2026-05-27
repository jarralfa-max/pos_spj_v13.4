from pathlib import Path


VENTAS_PY = Path(__file__).resolve().parents[1] / "modulos" / "ventas.py"
SALES_SVC = Path(__file__).resolve().parents[1] / "core" / "services" / "sales_service.py"


def test_sales_service_has_pending_payment_factory():
    src = SALES_SVC.read_text(encoding="utf-8")
    assert "def create_pending_payment_sale(" in src
    assert "pendiente_pago" in src


def test_ui_mercadopago_pending_branch_does_not_execute_sale():
    src = VENTAS_PY.read_text(encoding="utf-8")
    start = src.find("if is_mercado_pago(datos_pago.get('forma_pago')):")
    assert start != -1
    block = src[start:start + 2500]
    assert "create_pending_payment_sale(" in block
    assert "mp.crear_link(" in block
    assert "self.cancelar_venta(silent=True)" in block
    assert "return" in block
    assert "execute_sale(" not in block


def test_ui_pending_branch_does_not_open_drawer_or_publish_completed_event():
    src = VENTAS_PY.read_text(encoding="utf-8")
    start = src.find("if is_mercado_pago(datos_pago.get('forma_pago')):")
    assert start != -1
    block = src[start:start + 2500]
    assert "_abrir_cajon(" not in block
    assert "VENTA_COMPLETADA" not in block
