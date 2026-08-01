from types import SimpleNamespace

from frontend.desktop.modules.purchasing.navigation import (
    PurchasingRoutes,
    visible_routes,
)


def capabilities(**grants):
    defaults = {
        "module_view": False, "requisition_view": False, "order_view": False,
        "direct_view": False, "receipt_view": False, "invoice_view": False,
        "origin_view": False,
    }
    defaults.update(grants)
    return SimpleNamespace(**defaults)


def test_navigation_is_empty_without_module_view():
    assert visible_routes(capabilities()) == ()


def test_navigation_contains_only_granted_implemented_routes():
    routes = visible_routes(capabilities(
        module_view=True, requisition_view=True, invoice_view=True))

    assert [route.key for route in routes] == [
        PurchasingRoutes.DASHBOARD,
        PurchasingRoutes.REQUISITIONS,
        PurchasingRoutes.INVOICES,
    ]
    assert [route.group for route in routes] == ["COMPRAS", "PLANEACIÓN", "FACTURACIÓN"]


def test_unimplemented_routes_are_not_in_navigation_catalog():
    keys = {route.key for route in visible_routes(capabilities(
        module_view=True, requisition_view=True, order_view=True, direct_view=True,
        receipt_view=True, origin_view=True, invoice_view=True))}

    assert "rfq" not in keys
    assert "awards" not in keys
    assert "settings" not in keys


def test_origin_loading_does_not_inherit_receiving_permission():
    receiver_keys = {route.key for route in visible_routes(capabilities(
        module_view=True, receipt_view=True))}
    logistics_keys = {route.key for route in visible_routes(capabilities(
        module_view=True, origin_view=True))}

    assert PurchasingRoutes.RECEIPTS in receiver_keys
    assert PurchasingRoutes.ORIGIN_LOADING not in receiver_keys
    assert PurchasingRoutes.ORIGIN_LOADING in logistics_keys
