from pathlib import Path


VENTAS_PY = Path(__file__).resolve().parents[1] / "modulos" / "ventas.py"


def test_finalizar_venta_does_not_publish_ajuste_inventario():
    src = VENTAS_PY.read_text(encoding="utf-8")
    start = src.find("def finalizar_venta")
    assert start != -1
    block = src[start:start + 12000]
    assert "publish(AJUSTE_INVENTARIO" not in block


def test_finalizar_venta_does_not_publish_stock_actualizado_business_event():
    src = VENTAS_PY.read_text(encoding="utf-8")
    start = src.find("def finalizar_venta")
    assert start != -1
    block = src[start:start + 12000]
    assert "publish(STOCK_ACTUALIZADO" not in block


def test_ui_refreshes_products_locally_after_sale():
    src = VENTAS_PY.read_text(encoding="utf-8")
    start = src.find("def finalizar_venta")
    assert start != -1
    block = src[start:start + 12000]
    assert "self.cargar_productos_interactivos()" in block
