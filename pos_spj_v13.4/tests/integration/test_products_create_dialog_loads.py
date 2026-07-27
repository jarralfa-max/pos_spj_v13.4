from __future__ import annotations

from tests.integration.test_product_dialog_dependencies import _app, _container, _products_module


def test_products_create_dialog_loads_without_attribute_error() -> None:
    _app()
    DialogoProducto = _products_module()

    dialog = DialogoProducto(_container())

    assert dialog.windowTitle() == "Nuevo Producto"
