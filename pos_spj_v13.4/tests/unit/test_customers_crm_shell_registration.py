"""SHELL-16 — customers_crm's registration into the new shell (module
descriptor, route definition, activator). Pure-Python; no Qt/DB needed —
the activator only registers a factory closure, it never invokes it.
"""
from __future__ import annotations

import inspect

from frontend.desktop.modules.customers_crm.shell_registration import (
    CUSTOMERS_CRM_MODULE_ID,
    CUSTOMERS_CRM_REQUIRED_PERMISSION,
    CUSTOMERS_CRM_ROUTE_ID,
    CUSTOMERS_CRM_VIEW_FACTORY_ID,
    CustomersCrmModuleActivator,
    build_customers_crm_module_descriptor,
    build_customers_crm_route_definition,
)
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def test_required_permission_matches_the_real_catalog_code():
    assert CUSTOMERS_CRM_REQUIRED_PERMISSION == "CLIENTES_CRM.ver"


def test_module_descriptor_fields():
    descriptor = build_customers_crm_module_descriptor()
    assert descriptor.module_id == CUSTOMERS_CRM_MODULE_ID
    assert descriptor.display_name == "Clientes y CRM"
    assert descriptor.startup_mode is StartupMode.LAZY
    assert descriptor.routes == (CUSTOMERS_CRM_ROUTE_ID,)
    assert CUSTOMERS_CRM_REQUIRED_PERMISSION in descriptor.permissions


def test_route_definition_fields():
    route = build_customers_crm_route_definition()
    assert route.route_id == CUSTOMERS_CRM_ROUTE_ID
    assert route.module_id == CUSTOMERS_CRM_MODULE_ID
    assert route.view_factory_id == CUSTOMERS_CRM_VIEW_FACTORY_ID
    assert route.required_permission == CUSTOMERS_CRM_REQUIRED_PERMISSION
    assert route.breadcrumb == ("Clientes", "Clientes y CRM")


def test_route_id_does_not_collide_with_the_internal_customers_or_crm_namespace():
    # customers_crm_routes.py's own internal tab-routes use the
    # "customers."/"crm." prefixes (CRM-1 guardrail) — the shell-level
    # route for the whole module must not collide with that namespace.
    assert not CUSTOMERS_CRM_ROUTE_ID.startswith("customers.")
    assert not CUSTOMERS_CRM_ROUTE_ID.startswith("crm.")
    assert "." in CUSTOMERS_CRM_ROUTE_ID


def test_activator_registers_the_view_factory_under_the_expected_id():
    registry = ViewFactoryRegistry()
    activator = CustomersCrmModuleActivator(connection=object(), view_factory_registry=registry)
    assert registry.is_registered(CUSTOMERS_CRM_VIEW_FACTORY_ID) is False
    activator.activate(build_customers_crm_module_descriptor())
    assert registry.is_registered(CUSTOMERS_CRM_VIEW_FACTORY_ID) is True


def test_activator_does_not_construct_the_view_eagerly():
    calls = []

    class ExplodingConnection:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("the connection must not be touched during activate()")

    registry = ViewFactoryRegistry()
    activator = CustomersCrmModuleActivator(connection=ExplodingConnection(), view_factory_registry=registry)
    activator.activate(build_customers_crm_module_descriptor())  # must not raise
    assert calls == []


def test_activator_never_receives_a_whole_container():
    params = list(inspect.signature(CustomersCrmModuleActivator.__init__).parameters)
    assert "container" not in params
    assert {"connection", "view_factory_registry", "session_context"} <= set(params)
