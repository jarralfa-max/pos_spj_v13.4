"""SHELL-16 — purchasing's registration into the new shell (module
descriptor, route definition, activator). Pure-Python; no Qt/DB needed —
the activator only registers a factory closure, it never invokes it.
"""
from __future__ import annotations

import inspect

from frontend.desktop.modules.purchasing.shell_registration import (
    PURCHASING_MODULE_ID,
    PURCHASING_REQUIRED_PERMISSION,
    PURCHASING_ROUTE_ID,
    PURCHASING_VIEW_FACTORY_ID,
    PurchasingModuleActivator,
    build_purchasing_module_descriptor,
    build_purchasing_route_definition,
)
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def test_required_permission_matches_the_real_catalog_code():
    assert PURCHASING_REQUIRED_PERMISSION == "COMPRAS.ver"


def test_module_descriptor_fields():
    descriptor = build_purchasing_module_descriptor()
    assert descriptor.module_id == PURCHASING_MODULE_ID
    assert descriptor.display_name == "Compras"
    assert descriptor.startup_mode is StartupMode.LAZY
    assert descriptor.routes == (PURCHASING_ROUTE_ID,)
    assert PURCHASING_REQUIRED_PERMISSION in descriptor.permissions


def test_route_definition_fields():
    route = build_purchasing_route_definition()
    assert route.route_id == PURCHASING_ROUTE_ID
    assert route.module_id == PURCHASING_MODULE_ID
    assert route.view_factory_id == PURCHASING_VIEW_FACTORY_ID
    assert route.required_permission == PURCHASING_REQUIRED_PERMISSION
    assert route.breadcrumb == ("Compras",)


def test_activator_registers_the_view_factory_under_the_expected_id():
    registry = ViewFactoryRegistry()
    activator = PurchasingModuleActivator(connection=object(), view_factory_registry=registry)
    assert registry.is_registered(PURCHASING_VIEW_FACTORY_ID) is False
    activator.activate(build_purchasing_module_descriptor())
    assert registry.is_registered(PURCHASING_VIEW_FACTORY_ID) is True


def test_activator_does_not_construct_the_view_eagerly():
    calls = []

    class ExplodingConnection:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("the connection must not be touched during activate()")

    registry = ViewFactoryRegistry()
    activator = PurchasingModuleActivator(connection=ExplodingConnection(), view_factory_registry=registry)
    activator.activate(build_purchasing_module_descriptor())  # must not raise
    assert calls == []


def test_activator_never_receives_a_whole_container():
    params = list(inspect.signature(PurchasingModuleActivator.__init__).parameters)
    assert "container" not in params
    assert {
        "connection", "view_factory_registry", "session_context",
        "logistics_service", "logistics_queries",
    } <= set(params)
