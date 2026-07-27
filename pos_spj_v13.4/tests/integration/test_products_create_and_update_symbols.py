from __future__ import annotations

from tests.integration.test_product_dialog_dependencies import _app, _container, _products_module


def test_product_create_and_update_symbols_are_available() -> None:
    _app()
    DialogoProducto = _products_module()

    create_dialog = DialogoProducto(_container())
    update_dialog = DialogoProducto(_container(), producto_id=1)

    for dialog in (create_dialog, update_dialog):
        assert dialog.product_type_policy is not None
        assert dialog.create_product_use_case is not None
        assert dialog.update_product_use_case is not None
