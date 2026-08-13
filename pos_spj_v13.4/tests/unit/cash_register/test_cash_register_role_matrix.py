"""Enterprise role matrix for Caja.

Roles are grant templates only. Authorization remains exact ``CAJA.accion``
through the live session checker and UI capabilities.
"""

from __future__ import annotations

import unittest

from backend.application.cash_register.permissions import CashPermissions as P
from backend.application.cash_register.session_authorization import CashSessionPermissionChecker
from frontend.desktop.modules.cash_register.capability_resolver import resolve_cash_capabilities
from frontend.desktop.modules.cash_register.cash_register_routes import visible_routes


ROLE_GRANTS = {
    "solo_lectura": {
        P.ACCESS,
        P.SHIFT_VIEW,
        P.MOVEMENT_VIEW,
        P.BLIND_COUNT_VIEW,
        P.X_CUT_VIEW,
        P.Z_CUT_VIEW,
        P.DIFFERENCE_VIEW,
        P.HANDOVER_VIEW,
        P.DEPOSIT_VIEW,
        P.REFUND_VIEW,
        P.DRAWER_EVENT_VIEW,
    },
    "cajero": {
        P.ACCESS,
        P.VIEW_OWN_BRANCH,
        P.SHIFT_VIEW,
        P.SHIFT_OPEN,
        P.SHIFT_SUSPEND,
        P.SHIFT_RESUME,
        P.SHIFT_PREPARE_CLOSE,
        P.SHIFT_CLOSE,
        P.MOVEMENT_VIEW,
        P.MOVEMENT_INCOME,
        P.MOVEMENT_WITHDRAWAL,
        P.BLIND_COUNT_VIEW,
        P.BLIND_COUNT_START,
        P.BLIND_COUNT_CAPTURE,
        P.BLIND_COUNT_CONFIRM,
        P.X_CUT_VIEW,
        P.X_CUT_GENERATE,
        P.HANDOVER_VIEW,
        P.HANDOVER_PREPARE,
        P.HANDOVER_DELIVER,
        P.REFUND_VIEW,
        P.REFUND_REQUEST,
        P.DRAWER_OPEN,
        P.PRINT,
    },
    "supervisor_caja": {
        P.ACCESS,
        P.VIEW_SENSITIVE_AMOUNTS,
        P.SHIFT_VIEW,
        P.SHIFT_FORCE_CLOSE,
        P.SHIFT_REASSIGN,
        P.MOVEMENT_VIEW,
        P.MOVEMENT_AUTHORIZE_OVER_LIMIT,
        P.MOVEMENT_REVERSE,
        P.BLIND_COUNT_VIEW,
        P.BLIND_COUNT_REVEAL_EXPECTED,
        P.BLIND_COUNT_OVERRIDE,
        P.Z_CUT_VIEW,
        P.Z_CUT_GENERATE,
        P.Z_CUT_REVIEW,
        P.DIFFERENCE_VIEW,
        P.DIFFERENCE_REVIEW,
        P.DIFFERENCE_RESOLVE,
        P.SAFE_DROP_AUTHORIZE,
        P.REFUND_VIEW,
        P.REFUND_AUTHORIZE,
        P.DRAWER_OPEN_WITHOUT_SALE,
    },
    "receptor_valores": {
        P.ACCESS,
        P.HANDOVER_VIEW,
        P.HANDOVER_RECEIVE,
        P.HANDOVER_DISPUTE,
    },
    "auditor_caja": {
        P.ACCESS,
        P.VIEW_ALL_BRANCHES,
        P.VIEW_SENSITIVE_AMOUNTS,
        P.AUDIT_VIEW,
        P.EXPORT,
        P.SHIFT_VIEW,
        P.MOVEMENT_VIEW,
        P.BLIND_COUNT_VIEW,
        P.X_CUT_VIEW,
        P.Z_CUT_VIEW,
        P.DIFFERENCE_VIEW,
        P.HANDOVER_VIEW,
        P.DEPOSIT_VIEW,
        P.REFUND_VIEW,
        P.DRAWER_EVENT_VIEW,
        P.HARDWARE_VIEW,
        P.NOTIFICATIONS_VIEW,
        P.SETTINGS_VIEW,
        P.SYNC_VIEW,
    },
    "administrador_configuracion_caja": {
        P.ACCESS,
        P.REGISTER_VIEW,
        P.REGISTER_CREATE,
        P.REGISTER_EDIT,
        P.REGISTER_ACTIVATE,
        P.REGISTER_BLOCK,
        P.SETTINGS_VIEW,
        P.SETTINGS_MANAGE,
        P.PAYMENT_METHOD_VIEW,
        P.PAYMENT_METHOD_MANAGE,
        P.NOTIFICATIONS_VIEW,
        P.NOTIFICATIONS_MANAGE,
    },
    "administrador_hardware_caja": {
        P.ACCESS,
        P.DRAWER_VIEW,
        P.DRAWER_MANAGE,
        P.TERMINAL_VIEW,
        P.TERMINAL_MANAGE,
        P.HARDWARE_VIEW,
        P.HARDWARE_DIAGNOSE,
        P.HARDWARE_MANAGE,
    },
}


class _Session:
    is_active = True
    user_id = "user-1"
    active_branch_id = "branch-1"

    def __init__(self, grants: set[str]) -> None:
        self._grants = set(grants)

    def tiene_permiso(self, permission_code: str) -> bool:
        return permission_code in self._grants


def _capabilities(role: str):
    return resolve_cash_capabilities(_Session(ROLE_GRANTS[role]).tiene_permiso)


class CashRegisterRoleMatrixTests(unittest.TestCase):
    def assertBackendAndUi(self, role: str, permission: str, capability: str, expected: bool):
        session = _Session(ROLE_GRANTS[role])
        checker = CashSessionPermissionChecker(session)
        self.assertIs(checker.has_permission("user-1", permission), expected)
        self.assertIs(getattr(resolve_cash_capabilities(session.tiene_permiso), capability), expected)

    def test_roles_are_exact_templates(self):
        self.assertEqual(
            set(ROLE_GRANTS),
            {
                "solo_lectura",
                "cajero",
                "supervisor_caja",
                "receptor_valores",
                "auditor_caja",
                "administrador_configuracion_caja",
                "administrador_hardware_caja",
            },
        )
        for grants in ROLE_GRANTS.values():
            self.assertTrue(all(code.startswith("CAJA.") for code in grants))
            self.assertFalse(any(code.startswith("CASH_") for code in grants))

    def test_read_only_sees_views_without_mutations(self):
        caps = _capabilities("solo_lectura")
        self.assertEqual(
            {route.key for route in visible_routes(caps)},
            {
                "overview",
                "shifts",
                "ledger",
                "blind_count",
                "x_cut",
                "z_cut",
                "differences",
                "handover",
                "deposits",
                "refunds",
                "drawer_events",
            },
        )
        self.assertBackendAndUi("solo_lectura", P.MOVEMENT_WITHDRAWAL, "movement_withdrawal", False)
        self.assertBackendAndUi("solo_lectura", P.DIFFERENCE_RESOLVE, "difference_resolve", False)

    def test_cashier_can_operate_shift_and_ledger_but_not_sensitive_overrides(self):
        self.assertBackendAndUi("cajero", P.SHIFT_OPEN, "shift_open", True)
        self.assertBackendAndUi("cajero", P.MOVEMENT_INCOME, "movement_income", True)
        self.assertBackendAndUi("cajero", P.SHIFT_FORCE_CLOSE, "shift_force_close", False)
        self.assertBackendAndUi("cajero", P.DIFFERENCE_RESOLVE, "difference_resolve", False)
        self.assertBackendAndUi("cajero", P.BLIND_COUNT_REVEAL_EXPECTED, "count_reveal_expected", False)
        self.assertBackendAndUi("cajero", P.DRAWER_OPEN_WITHOUT_SALE, "drawer_open_without_sale", False)

    def test_supervisor_authorizes_exceptions_without_hardware_admin(self):
        self.assertBackendAndUi(
            "supervisor_caja",
            P.MOVEMENT_AUTHORIZE_OVER_LIMIT,
            "movement_authorize_over_limit",
            True,
        )
        self.assertBackendAndUi("supervisor_caja", P.SHIFT_FORCE_CLOSE, "shift_force_close", True)
        self.assertBackendAndUi("supervisor_caja", P.HARDWARE_MANAGE, "hardware_manage", False)

    def test_value_receiver_receives_but_does_not_prepare_or_reverse_money(self):
        self.assertBackendAndUi("receptor_valores", P.HANDOVER_RECEIVE, "handover_receive", True)
        self.assertBackendAndUi("receptor_valores", P.HANDOVER_PREPARE, "handover_prepare", False)
        self.assertBackendAndUi("receptor_valores", P.MOVEMENT_REVERSE, "movement_reverse", False)

    def test_auditor_views_without_mutations(self):
        caps = _capabilities("auditor_caja")
        self.assertIn("hardware", {route.key for route in visible_routes(caps)})
        self.assertBackendAndUi("auditor_caja", P.EXPORT, "module_view", True)
        self.assertBackendAndUi("auditor_caja", P.REFUND_EXECUTE, "refund_execute", False)
        self.assertBackendAndUi("auditor_caja", P.SETTINGS_MANAGE, "settings_manage", False)

    def test_configuration_admin_does_not_get_financial_authority(self):
        self.assertBackendAndUi("administrador_configuracion_caja", P.SETTINGS_MANAGE, "settings_manage", True)
        self.assertBackendAndUi("administrador_configuracion_caja", P.DIFFERENCE_RESOLVE, "difference_resolve", False)
        self.assertBackendAndUi("administrador_configuracion_caja", P.MOVEMENT_AUTHORIZE_OVER_LIMIT, "movement_authorize_over_limit", False)

    def test_hardware_admin_has_no_money_privileges(self):
        self.assertBackendAndUi("administrador_hardware_caja", P.HARDWARE_MANAGE, "hardware_manage", True)
        self.assertBackendAndUi("administrador_hardware_caja", P.MOVEMENT_WITHDRAWAL, "movement_withdrawal", False)
        self.assertBackendAndUi("administrador_hardware_caja", P.REFUND_AUTHORIZE, "refund_authorize", False)


if __name__ == "__main__":
    unittest.main()
