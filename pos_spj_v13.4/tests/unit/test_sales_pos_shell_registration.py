"""SHELL-16 — sales_pos's registration into the new shell (module descriptor,
route definition, activator). Pure-Python; no Qt/DB needed — the activator
only registers a factory closure, it never invokes it.
"""
from __future__ import annotations

from frontend.desktop.modules.sales_pos.shell_registration import (
    SALES_POS_MODULE_ID,
    SALES_POS_REQUIRED_PERMISSION,
    SALES_POS_ROUTE_ID,
    SALES_POS_VIEW_FACTORY_ID,
    SalesPosModuleActivator,
    build_sales_pos_module_descriptor,
    build_sales_pos_route_definition,
)
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def test_required_permission_matches_the_real_catalog_code():
    assert SALES_POS_REQUIRED_PERMISSION == "POS.ver"


def test_module_descriptor_fields():
    descriptor = build_sales_pos_module_descriptor()
    assert descriptor.module_id == SALES_POS_MODULE_ID
    assert descriptor.display_name == "Punto de Venta"
    assert descriptor.startup_mode is StartupMode.LAZY
    assert descriptor.routes == (SALES_POS_ROUTE_ID,)
    assert SALES_POS_REQUIRED_PERMISSION in descriptor.permissions


def test_route_definition_fields():
    route = build_sales_pos_route_definition()
    assert route.route_id == SALES_POS_ROUTE_ID
    assert route.module_id == SALES_POS_MODULE_ID
    assert route.view_factory_id == SALES_POS_VIEW_FACTORY_ID
    assert route.required_permission == SALES_POS_REQUIRED_PERMISSION
    assert route.breadcrumb == ("Ventas", "Punto de Venta")


def test_route_id_is_dotted_not_the_ambiguous_legacy_code():
    # RouteRegistryValidator (SHELL-9) rejects bare legacy codes like "POS" —
    # the real navigation route id must not collide with that.
    assert "." in SALES_POS_ROUTE_ID
    assert SALES_POS_ROUTE_ID != "POS"


def test_activator_registers_the_view_factory_under_the_expected_id():
    registry = ViewFactoryRegistry()
    activator = SalesPosModuleActivator(connection=object(), view_factory_registry=registry)
    assert registry.is_registered(SALES_POS_VIEW_FACTORY_ID) is False
    activator.activate(build_sales_pos_module_descriptor())
    assert registry.is_registered(SALES_POS_VIEW_FACTORY_ID) is True


def test_activator_does_not_construct_the_view_eagerly():
    calls = []

    class ExplodingConnection:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("the connection must not be touched during activate()")

    registry = ViewFactoryRegistry()
    activator = SalesPosModuleActivator(connection=ExplodingConnection(), view_factory_registry=registry)
    activator.activate(build_sales_pos_module_descriptor())  # must not raise
    assert calls == []


def test_activator_never_receives_or_mentions_a_whole_container():
    # Structural guard for this file's own responsibility — the real
    # "no AppContainer" guardrail already covers frontend/desktop/modules/sales_pos/
    # (tests/architecture/test_sales_pos_ui_does_not_receive_app_container.py);
    # this just documents the constructor's actual explicit parameter names.
    import inspect

    params = list(inspect.signature(SalesPosModuleActivator.__init__).parameters)
    assert "container" not in params
    assert {"connection", "view_factory_registry", "session_context", "printer_service"} <= set(params)
