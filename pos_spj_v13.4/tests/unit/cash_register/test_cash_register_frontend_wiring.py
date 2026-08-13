import unittest
from decimal import Decimal

from backend.application.cash_register.permissions import CashPermissions
from frontend.desktop.modules.cash_register.capability_resolver import resolve_cash_capabilities
from frontend.desktop.modules.cash_register.cash_register_presenter import (
    CashRegisterPresenter,
)
from frontend.desktop.modules.cash_register.cash_register_routes import CASH_REGISTER_ROUTES
from frontend.desktop.modules.cash_register.cash_register_routes import grouped_routes
from frontend.desktop.modules.cash_register.cash_register_routes import visible_routes
from frontend.desktop.modules.cash_register.view_models import CashCapabilities


class _Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def __init__(self, grants):
        self._grants = set(grants)

    def tiene_permiso(self, code):
        return code in self._grants


class _Container:
    pass


class _ContextSession(_Session):
    branch_id = "branch-1"


class CashRegisterFrontendWiringTests(unittest.TestCase):
    def test_cash_routes_use_backend_permission_catalog(self):
        codes = {route.required_permission for route in CASH_REGISTER_ROUTES}
        self.assertIn(CashPermissions.ACCESS, codes)
        self.assertIn(CashPermissions.SETTINGS_VIEW, codes)
        self.assertTrue(all(code.startswith("CAJA.") for code in codes))
        self.assertFalse(any(code.startswith("CASH_") or code.startswith("cash_register.") for code in codes))
        capability_fields = set(CashCapabilities.__dataclass_fields__)
        self.assertLessEqual({route.capability for route in CASH_REGISTER_ROUTES}, capability_fields)

    def test_cash_navigation_uses_view_capabilities_not_action_permissions(self):
        capabilities = resolve_cash_capabilities(_Session({
            CashPermissions.ACCESS,
            CashPermissions.BLIND_COUNT_START,
            CashPermissions.HANDOVER_PREPARE,
            CashPermissions.REFUND_REQUEST,
            CashPermissions.HARDWARE_DIAGNOSE,
        }).tiene_permiso)
        self.assertEqual({route.key for route in visible_routes(capabilities)}, {"overview"})

    def test_cash_navigation_is_empty_without_module_view(self):
        capabilities = resolve_cash_capabilities(_Session({
            CashPermissions.SHIFT_VIEW,
            CashPermissions.MOVEMENT_VIEW,
            CashPermissions.SETTINGS_VIEW,
        }).tiene_permiso)
        visible = visible_routes(capabilities)
        self.assertEqual(visible, ())
        self.assertEqual(grouped_routes(visible), [])

    def test_cash_presenter_resolves_capabilities_from_session_permissions(self):
        grants = {CashPermissions.ACCESS, CashPermissions.SETTINGS_VIEW}
        capabilities = resolve_cash_capabilities(_Session(grants).tiene_permiso)
        self.assertTrue(capabilities.module_view)
        self.assertTrue(capabilities.settings_view)
        self.assertFalse(capabilities.movement_view)

    def test_cash_presenter_exposes_backend_query_services_from_composition_root(self):
        presenter = CashRegisterPresenter(
            session_context=_Session({CashPermissions.ACCESS}),
            query_services={"configuration": object()},
            use_cases={"cash_open_shift_uc": object()},
        )
        self.assertIsNotNone(presenter.query_service("configuration"))
        self.assertIsNone(presenter.query_service("ledger"))
        self.assertIn("cash_open_shift_uc", presenter.backend_binding("shifts"))

    def test_cash_shift_presenter_commands_use_explicit_session_and_active_context(self):
        calls = {}

        def capture(name):
            def handler(**kwargs):
                calls[name] = kwargs
                return object()
            return handler

        presenter = CashRegisterPresenter(
            session_context=_ContextSession({CashPermissions.ACCESS}),
            command_handlers={
                "open_cash_shift": capture("open"),
                "suspend_cash_shift": capture("suspend"),
                "resume_cash_shift": capture("resume"),
                "begin_cash_shift_closing": capture("preclose"),
            },
            active_context_provider=lambda: {
                "cash_register_id": "register-1",
                "cash_drawer_id": "drawer-1",
                "pos_terminal_id": "terminal-1",
                "cash_shift_id": "shift-1",
            },
        )

        presenter.open_cash_shift(opening_amount=Decimal("250.00"))
        presenter.suspend_cash_shift(reason="Pausa operativa")
        presenter.resume_cash_shift()
        presenter.begin_cash_shift_closing()

        self.assertEqual(calls["open"]["branch_id"], "branch-1")
        self.assertEqual(calls["open"]["register_id"], "register-1")
        self.assertEqual(calls["open"]["drawer_id"], "drawer-1")
        self.assertEqual(calls["open"]["terminal_id"], "terminal-1")
        self.assertEqual(calls["open"]["cashier_user_id"], "user-1")
        self.assertEqual(calls["open"]["opening_amount"], Decimal("250.00"))
        self.assertEqual(calls["suspend"]["shift_id"], "shift-1")
        self.assertEqual(calls["suspend"]["reason"], "Pausa operativa")
        self.assertEqual(calls["resume"]["shift_id"], "shift-1")
        self.assertEqual(calls["preclose"]["shift_id"], "shift-1")

    def test_cash_configuration_presenter_command_uses_session_context(self):
        calls = {}

        def configure(**kwargs):
            calls.update(kwargs)
            return object()

        presenter = CashRegisterPresenter(
            session_context=_ContextSession({CashPermissions.ACCESS}),
            command_handlers={"configure_cash_register": configure},
        )
        presenter.configure_cash_register(
            section="limits",
            name="SAFE_DROP",
            value="100.00 / 500.00",
        )
        self.assertEqual(calls["branch_id"], "branch-1")
        self.assertEqual(calls["actor_user_id"], "user-1")
        self.assertEqual(calls["scope_type"], "SYSTEM")
        self.assertEqual(calls["section"], "limits")


if __name__ == "__main__":
    unittest.main()
