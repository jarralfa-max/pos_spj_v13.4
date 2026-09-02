"""SHELL-16 — inventory's registration into the new shell (module
descriptor, route definition, activator). Pure-Python; no Qt/DB needed —
the activator only registers a factory closure, it never invokes it.
"""
from __future__ import annotations

import inspect

from frontend.desktop.modules.inventory.shell_registration import (
    INVENTORY_MODULE_ID,
    INVENTORY_REQUIRED_PERMISSION,
    INVENTORY_ROUTE_ID,
    INVENTORY_VIEW_FACTORY_ID,
    InventoryModuleActivator,
    build_inventory_module_descriptor,
    build_inventory_route_definition,
)
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def test_required_permission_matches_the_real_catalog_code():
    assert INVENTORY_REQUIRED_PERMISSION == "INVENTARIO.ver"


def test_module_descriptor_fields():
    descriptor = build_inventory_module_descriptor()
    assert descriptor.module_id == INVENTORY_MODULE_ID
    assert descriptor.display_name == "Inventario"
    assert descriptor.startup_mode is StartupMode.LAZY
    assert descriptor.routes == (INVENTORY_ROUTE_ID,)
    assert INVENTORY_REQUIRED_PERMISSION in descriptor.permissions


def test_route_definition_fields():
    route = build_inventory_route_definition()
    assert route.route_id == INVENTORY_ROUTE_ID
    assert route.module_id == INVENTORY_MODULE_ID
    assert route.view_factory_id == INVENTORY_VIEW_FACTORY_ID
    assert route.required_permission == INVENTORY_REQUIRED_PERMISSION
    assert route.breadcrumb == ("Inventario",)


def test_activator_registers_the_view_factory_under_the_expected_id():
    registry = ViewFactoryRegistry()
    activator = InventoryModuleActivator(connection=object(), view_factory_registry=registry)
    assert registry.is_registered(INVENTORY_VIEW_FACTORY_ID) is False
    activator.activate(build_inventory_module_descriptor())
    assert registry.is_registered(INVENTORY_VIEW_FACTORY_ID) is True


def test_activator_does_not_construct_the_view_eagerly():
    calls = []

    class ExplodingConnection:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("the connection must not be touched during activate()")

    registry = ViewFactoryRegistry()
    activator = InventoryModuleActivator(connection=ExplodingConnection(), view_factory_registry=registry)
    activator.activate(build_inventory_module_descriptor())  # must not raise
    assert calls == []


def test_activator_never_receives_a_whole_container():
    params = list(inspect.signature(InventoryModuleActivator.__init__).parameters)
    assert "container" not in params
    assert {"connection", "view_factory_registry", "session_context"} <= set(params)
