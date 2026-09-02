"""SHELL-16 — cash_register's registration into the new shell (module
descriptor, route definition, activator, composition stand-in). Pure-Python;
no Qt/DB needed — the activator only registers a factory closure, it
never invokes it.
"""
from __future__ import annotations

import inspect

from frontend.desktop.modules.cash_register.shell_registration import (
    CASH_REGISTER_MODULE_ID,
    CASH_REGISTER_REQUIRED_PERMISSION,
    CASH_REGISTER_ROUTE_ID,
    CASH_REGISTER_VIEW_FACTORY_ID,
    CashRegisterModuleActivator,
    _CashRegisterCompositionStandIn,
    build_cash_register_module_descriptor,
    build_cash_register_route_definition,
)
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def test_required_permission_matches_the_real_catalog_code():
    assert CASH_REGISTER_REQUIRED_PERMISSION == "CAJA.ver"


def test_module_descriptor_fields():
    descriptor = build_cash_register_module_descriptor()
    assert descriptor.module_id == CASH_REGISTER_MODULE_ID
    assert descriptor.display_name == "Caja"
    assert descriptor.startup_mode is StartupMode.LAZY
    assert descriptor.routes == (CASH_REGISTER_ROUTE_ID,)
    assert CASH_REGISTER_REQUIRED_PERMISSION in descriptor.permissions


def test_route_definition_fields():
    route = build_cash_register_route_definition()
    assert route.route_id == CASH_REGISTER_ROUTE_ID
    assert route.module_id == CASH_REGISTER_MODULE_ID
    assert route.view_factory_id == CASH_REGISTER_VIEW_FACTORY_ID
    assert route.required_permission == CASH_REGISTER_REQUIRED_PERMISSION
    assert route.breadcrumb == ("Caja",)


def test_stand_in_only_exposes_db_and_session():
    stand_in = _CashRegisterCompositionStandIn(connection="conn", session_context="sess")
    assert stand_in.db == "conn"
    assert stand_in.session == "sess"
    # Nothing else — every optional override the factory's getattr(..., None)
    # looks for must be genuinely absent, not present-but-None (a real
    # container attribute vs. a missing one both satisfy getattr's default,
    # but this documents the stand-in never pretends to have more).
    assert vars(stand_in).keys() == {"db", "session"}


def test_stand_in_supports_setattr_for_the_factorys_cache_slots():
    # cash_register_factory.py writes active_cash_shift_id/active_cash_count_id
    # onto the composition root as a same-session cache — the stand-in must
    # be a plain mutable object, not something that rejects new attributes.
    stand_in = _CashRegisterCompositionStandIn(connection="conn")
    stand_in.active_cash_shift_id = "shift-1"
    assert stand_in.active_cash_shift_id == "shift-1"


def test_activator_registers_the_view_factory_under_the_expected_id():
    registry = ViewFactoryRegistry()
    activator = CashRegisterModuleActivator(connection=object(), view_factory_registry=registry)
    assert registry.is_registered(CASH_REGISTER_VIEW_FACTORY_ID) is False
    activator.activate(build_cash_register_module_descriptor())
    assert registry.is_registered(CASH_REGISTER_VIEW_FACTORY_ID) is True


def test_activator_does_not_construct_the_view_eagerly():
    calls = []

    class ExplodingConnection:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("the connection must not be touched during activate()")

    registry = ViewFactoryRegistry()
    activator = CashRegisterModuleActivator(connection=ExplodingConnection(), view_factory_registry=registry)
    activator.activate(build_cash_register_module_descriptor())  # must not raise
    assert calls == []


def test_activator_never_receives_a_whole_container():
    params = list(inspect.signature(CashRegisterModuleActivator.__init__).parameters)
    assert "container" not in params
    assert "composition_root" not in params
    assert {"connection", "view_factory_registry", "session_context"} <= set(params)
