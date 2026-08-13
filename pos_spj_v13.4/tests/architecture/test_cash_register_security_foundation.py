"""CASH-1 guardrails for the canonical Cash Register security boundary."""
import ast
from pathlib import Path
import unittest

from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions
from frontend.desktop.modules.cash_register.capability_resolver import resolve_cash_capabilities


REPO = Path(__file__).resolve().parents[2]
ROOTS = (
    REPO / "backend" / "application" / "cash_register",
    REPO / "backend" / "domain" / "cash_register",
)
SECURITY_ROOTS = ROOTS + (REPO / "frontend" / "desktop" / "modules" / "cash_register",)


class CashRegisterSecurityArchitectureTests(unittest.TestCase):
    def test_permission_catalog_is_granular(self):
        required = {
            "CAJA.turno.abrir", "CAJA.turno.cerrar", "CAJA.movimiento.retiro",
            "CAJA.conteo.confirmar", "CAJA.corte_z.generar",
            "CAJA.diferencia.resolver", "CAJA.entrega.recibir",
            "CAJA.reembolso.autorizar", "CAJA.cajon.abrir_sin_venta",
        }
        self.assertTrue(required <= ALL_CASH_PERMISSIONS)
        self.assertTrue({"ADMIN_CAJA", "PUEDE_CERRAR_CAJA"}.isdisjoint(
            ALL_CASH_PERMISSIONS))

    def test_security_foundation_has_no_float_contracts_or_legacy_permissions(self):
        offenders = []
        legacy = {"CAJA", "ADMIN_CAJA", "PUEDE_CERRAR_CAJA", "PUEDE_VER_CORTE"}
        for root in ROOTS:
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, float):
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: float literal")
                    if isinstance(node, ast.Constant) and node.value in legacy:
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.value}")
        self.assertFalse(offenders, "\n".join(offenders))

    def test_authorization_has_no_role_name_or_admin_shortcut(self):
        offenders = []
        forbidden_names = {"role", "roles", "rol", "admin", "supervisor", "is_admin"}
        forbidden_values = {"admin", "supervisor", "supervisor_caja", "cajero"}
        for root in SECURITY_ROOTS:
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Compare):
                        names = {
                            item.id for item in ast.walk(node)
                            if isinstance(item, ast.Name) and item.id.lower() in forbidden_names
                        }
                        values = {
                            str(item.value).lower() for item in ast.walk(node)
                            if isinstance(item, ast.Constant) and isinstance(item.value, str)
                        } & forbidden_values
                        if names or values:
                            offenders.append(
                                f"{path.relative_to(REPO)}:{node.lineno}: role/admin shortcut"
                            )
        self.assertFalse(offenders, "\n".join(offenders))

    def test_ui_backend_authorization_parity_for_every_cash_capability(self):
        mapping = {
            "module_view": CashPermissions.ACCESS,
            "register_view": CashPermissions.REGISTER_VIEW,
            "register_create": CashPermissions.REGISTER_CREATE,
            "register_edit": CashPermissions.REGISTER_EDIT,
            "register_activate": CashPermissions.REGISTER_ACTIVATE,
            "register_block": CashPermissions.REGISTER_BLOCK,
            "drawer_view": CashPermissions.DRAWER_VIEW,
            "drawer_manage": CashPermissions.DRAWER_MANAGE,
            "drawer_open": CashPermissions.DRAWER_OPEN,
            "drawer_open_without_sale": CashPermissions.DRAWER_OPEN_WITHOUT_SALE,
            "terminal_view": CashPermissions.TERMINAL_VIEW,
            "terminal_manage": CashPermissions.TERMINAL_MANAGE,
            "terminal_operate": CashPermissions.TERMINAL_OPERATE,
            "shift_view": CashPermissions.SHIFT_VIEW,
            "shift_open": CashPermissions.SHIFT_OPEN,
            "shift_suspend": CashPermissions.SHIFT_SUSPEND,
            "shift_resume": CashPermissions.SHIFT_RESUME,
            "shift_prepare_close": CashPermissions.SHIFT_PREPARE_CLOSE,
            "shift_close": CashPermissions.SHIFT_CLOSE,
            "shift_force_close": CashPermissions.SHIFT_FORCE_CLOSE,
            "shift_reassign": CashPermissions.SHIFT_REASSIGN,
            "movement_view": CashPermissions.MOVEMENT_VIEW,
            "movement_income": CashPermissions.MOVEMENT_INCOME,
            "movement_withdrawal": CashPermissions.MOVEMENT_WITHDRAWAL,
            "safe_drop_create": CashPermissions.MOVEMENT_SAFE_DROP,
            "movement_reverse": CashPermissions.MOVEMENT_REVERSE,
            "movement_authorize_over_limit": CashPermissions.MOVEMENT_AUTHORIZE_OVER_LIMIT,
            "count_view": CashPermissions.BLIND_COUNT_VIEW,
            "count_start": CashPermissions.BLIND_COUNT_START,
            "count_capture": CashPermissions.BLIND_COUNT_CAPTURE,
            "count_confirm": CashPermissions.BLIND_COUNT_CONFIRM,
            "count_reveal_expected": CashPermissions.BLIND_COUNT_REVEAL_EXPECTED,
            "count_cancel": CashPermissions.BLIND_COUNT_CANCEL,
            "count_override": CashPermissions.BLIND_COUNT_OVERRIDE,
            "x_cut_view": CashPermissions.X_CUT_VIEW,
            "x_cut_generate": CashPermissions.X_CUT_GENERATE,
            "x_cut_print": CashPermissions.X_CUT_PRINT,
            "x_cut_reprint": CashPermissions.X_CUT_REPRINT,
            "z_cut_view": CashPermissions.Z_CUT_VIEW,
            "z_cut_generate": CashPermissions.Z_CUT_GENERATE,
            "z_cut_review": CashPermissions.Z_CUT_REVIEW,
            "z_cut_print": CashPermissions.Z_CUT_PRINT,
            "z_cut_reprint": CashPermissions.Z_CUT_REPRINT,
            "difference_view": CashPermissions.DIFFERENCE_VIEW,
            "difference_explain": CashPermissions.DIFFERENCE_EXPLAIN,
            "difference_review": CashPermissions.DIFFERENCE_REVIEW,
            "difference_resolve": CashPermissions.DIFFERENCE_RESOLVE,
            "handover_view": CashPermissions.HANDOVER_VIEW,
            "handover_prepare": CashPermissions.HANDOVER_PREPARE,
            "handover_deliver": CashPermissions.HANDOVER_DELIVER,
            "handover_receive": CashPermissions.HANDOVER_RECEIVE,
            "handover_dispute": CashPermissions.HANDOVER_DISPUTE,
            "deposit_view": CashPermissions.DEPOSIT_VIEW,
            "deposit_prepare": CashPermissions.DEPOSIT_PREPARE,
            "payment_view": CashPermissions.PAYMENT_VIEW,
            "payment_method_view": CashPermissions.PAYMENT_METHOD_VIEW,
            "payment_method_manage": CashPermissions.PAYMENT_METHOD_MANAGE,
            "payment_terminal_view": CashPermissions.PAYMENT_TERMINAL_VIEW,
            "payment_terminal_manage": CashPermissions.PAYMENT_TERMINAL_MANAGE,
            "refund_view": CashPermissions.REFUND_VIEW,
            "refund_request": CashPermissions.REFUND_REQUEST,
            "refund_execute": CashPermissions.REFUND_EXECUTE,
            "refund_authorize": CashPermissions.REFUND_AUTHORIZE,
            "drawer_event_view": CashPermissions.DRAWER_EVENT_VIEW,
            "hardware_view": CashPermissions.HARDWARE_VIEW,
            "hardware_diagnose": CashPermissions.HARDWARE_DIAGNOSE,
            "hardware_manage": CashPermissions.HARDWARE_MANAGE,
            "notification_view": CashPermissions.NOTIFICATIONS_VIEW,
            "notification_manage": CashPermissions.NOTIFICATIONS_MANAGE,
            "audit_view": CashPermissions.AUDIT_VIEW,
            "settings_view": CashPermissions.SETTINGS_VIEW,
            "settings_manage": CashPermissions.SETTINGS_MANAGE,
            "sync_view": CashPermissions.SYNC_VIEW,
            "sync_manage": CashPermissions.SYNC_MANAGE,
        }
        capability_fields = set(resolve_cash_capabilities(lambda _: False).__dataclass_fields__)
        self.assertEqual(set(mapping), capability_fields)
        for capability, permission in mapping.items():
            caps = resolve_cash_capabilities(lambda code, granted=permission: code == granted)
            self.assertIs(getattr(caps, capability), True, capability)
            unexpected = [
                field for field in capability_fields - {capability}
                if getattr(caps, field)
            ]
            self.assertEqual(unexpected, [], f"{permission} unexpectedly grants {unexpected}")


if __name__ == "__main__":
    unittest.main()

