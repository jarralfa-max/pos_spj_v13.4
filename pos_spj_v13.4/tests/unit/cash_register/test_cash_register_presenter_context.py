"""Presenter session/device context contract for Caja."""

from __future__ import annotations

import unittest
from decimal import Decimal

from backend.application.cash_register.permissions import CashPermissions
from frontend.desktop.modules.cash_register.cash_register_presenter import (
    CashContextError,
    CashRegisterPresenter,
)


class _Session:
    def __init__(
        self,
        *,
        active: bool = True,
        user_id: str = "user-1",
        branch_id: str = "branch-1",
        grants: set[str] | None = None,
    ) -> None:
        self.is_active = active
        self.user_id = user_id
        self.active_branch_id = branch_id
        self._grants = grants or {CashPermissions.ACCESS}

    def tiene_permiso(self, code: str) -> bool:
        return code in self._grants


class CashRegisterPresenterContextTests(unittest.TestCase):
    def test_required_session_context_is_explicit_and_fail_closed(self):
        presenter = CashRegisterPresenter(session_context=_Session(active=False))

        with self.assertRaises(CashContextError):
            presenter.actor_user_id()

        presenter = CashRegisterPresenter(session_context=_Session(user_id="", branch_id=""))
        with self.assertRaises(CashContextError):
            presenter.actor_user_id()
        with self.assertRaises(CashContextError):
            presenter.active_branch_id()

    def test_required_cash_device_context_is_not_fabricated(self):
        presenter = CashRegisterPresenter(session_context=_Session())

        with self.assertRaises(CashContextError):
            presenter.active_register_id()
        with self.assertRaises(CashContextError):
            presenter.active_drawer_id()
        with self.assertRaises(CashContextError):
            presenter.active_terminal_id()
        with self.assertRaises(CashContextError):
            presenter.active_shift_id()

    def test_active_cash_context_is_injected_explicitly(self):
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            active_context_provider=lambda: {
                "cash_register_id": "register-1",
                "cash_drawer_id": "drawer-1",
                "pos_terminal_id": "terminal-1",
                "cash_shift_id": "shift-1",
            },
            active_shift_provider=lambda: "shift-1",
        )

        self.assertEqual(presenter.actor_user_id(), "user-1")
        self.assertEqual(presenter.active_branch_id(), "branch-1")
        self.assertEqual(presenter.active_register_id(), "register-1")
        self.assertEqual(presenter.active_drawer_id(), "drawer-1")
        self.assertEqual(presenter.active_terminal_id(), "terminal-1")
        self.assertEqual(presenter.active_shift_id(), "shift-1")
        self.assertEqual(presenter.optional_active_shift_id(), "shift-1")

    def test_ledger_command_uses_injected_handler_and_required_context(self):
        calls = []

        def handler(**kwargs):
            calls.append(kwargs)
            return "ok"

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={"register_cash_movement": handler},
            active_context_provider=lambda: {"cash_shift_id": "shift-1"},
            active_shift_provider=lambda: "shift-1",
        )

        self.assertEqual(
            presenter.register_cash_movement(
                movement_type="MANUAL_INCOME",
                amount=Decimal("125.50"),
                concept="Ingreso operativo",
                reason_code="EXCESS_CASH",
            ),
            "ok",
        )
        self.assertEqual(calls[0]["shift_id"], "shift-1")
        self.assertEqual(calls[0]["branch_id"], "branch-1")
        self.assertEqual(calls[0]["actor_user_id"], "user-1")
        self.assertEqual(calls[0]["amount"], Decimal("125.50"))
        self.assertEqual(calls[0]["reason_code"], "EXCESS_CASH")

    def test_ledger_command_fails_when_handler_is_missing(self):
        presenter = CashRegisterPresenter(session_context=_Session())
        with self.assertRaises(CashContextError):
            presenter.register_cash_movement(
                movement_type="MANUAL_INCOME",
                amount=Decimal("1.00"),
                concept="Ingreso",
            )

    def test_ledger_commands_pass_hot_authorization_actor(self):
        movement_calls = []
        reversal_calls = []

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "register_cash_movement": lambda **kwargs: movement_calls.append(kwargs) or "movement",
                "reverse_cash_movement": lambda **kwargs: reversal_calls.append(kwargs) or "reversal",
            },
            active_context_provider=lambda: {"cash_shift_id": "shift-1"},
            active_shift_provider=lambda: "shift-1",
        )

        self.assertEqual(
            presenter.register_cash_movement(
                movement_type="MANUAL_WITHDRAWAL",
                amount=Decimal("900.00"),
                concept="Retiro",
                authorized_by="supervisor-1",
            ),
            "movement",
        )
        self.assertEqual(movement_calls[0]["authorized_by"], "supervisor-1")

        self.assertEqual(
            presenter.reverse_cash_movement(
                entry_id="entry-1",
                authorized_by="supervisor-1",
                reason="Error de captura",
            ),
            "reversal",
        )
        self.assertEqual(reversal_calls[0]["authorized_by"], "supervisor-1")
        self.assertEqual(reversal_calls[0]["reason"], "Error de captura")

    def test_presenter_exposes_movement_reason_options_from_query_service(self):
        class _Reasons:
            def list_active(self, movement_type):
                return (movement_type,)

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            query_services={"movement_reasons": _Reasons()},
        )

        self.assertEqual(presenter.movement_reason_options("SAFE_DROP"), ("SAFE_DROP",))
        self.assertEqual(
            CashRegisterPresenter(session_context=_Session()).movement_reason_options("SAFE_DROP"),
            (),
        )

    def test_presenter_prepares_handover_with_injected_handler_and_denominations(self):
        calls = []

        class _Denominations:
            def list_active(self):
                return ("denom-50",)

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            query_services={"denominations": _Denominations()},
            command_handlers={"prepare_cash_handover": lambda **kwargs: calls.append(kwargs) or "handover"},
        )

        self.assertEqual(presenter.denomination_options(), ("denom-50",))
        self.assertEqual(
            presenter.prepare_cash_handover(
                safe_drop_entry_id="entry-1",
                denominations={"denom-50": 5},
            ),
            "handover",
        )
        self.assertEqual(calls[0]["safe_drop_entry_id"], "entry-1")
        self.assertEqual(calls[0]["branch_id"], "branch-1")
        self.assertEqual(calls[0]["actor_user_id"], "user-1")
        self.assertEqual(calls[0]["denominations"], {"denom-50": 5})

    def test_presenter_blind_count_workflow_commands(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "start_blind_count": lambda **kwargs: calls.append(("start", kwargs)) or "count",
                "capture_blind_count_denomination": (
                    lambda **kwargs: calls.append(("capture", kwargs)) or "captured"
                ),
                "confirm_blind_count": lambda **kwargs: calls.append(("confirm", kwargs)) or "confirmed",
            },
            active_context_provider=lambda: {"cash_shift_id": "shift-1"},
        )

        self.assertEqual(presenter.start_blind_count(), "count")
        self.assertEqual(
            presenter.capture_blind_count_denomination(
                count_id="count-1", denomination_id="denom-1", quantity=3),
            "captured",
        )
        self.assertEqual(presenter.confirm_blind_count(count_id="count-1"), "confirmed")
        self.assertEqual([name for name, _ in calls], ["start", "capture", "confirm"])
        self.assertEqual(calls[0][1]["shift_id"], "shift-1")
        self.assertEqual(calls[0][1]["counter_user_id"], "user-1")
        self.assertEqual(calls[1][1]["denomination_id"], "denom-1")
        self.assertEqual(calls[1][1]["quantity"], 3)
        self.assertEqual(calls[2][1]["actor_user_id"], "user-1")

    def test_presenter_handover_delivery_receive_and_dispute_commands(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "deliver_cash_handover": lambda **kwargs: calls.append(("deliver", kwargs)) or "delivered",
                "receive_cash_handover": lambda **kwargs: calls.append(("receive", kwargs)) or "received",
                "dispute_cash_handover": lambda **kwargs: calls.append(("dispute", kwargs)) or "disputed",
            },
        )

        self.assertEqual(
            presenter.deliver_cash_handover(handover_id="handover-1", denominations={"d50": 5}),
            "delivered",
        )
        self.assertEqual(
            presenter.receive_cash_handover(handover_id="handover-1", denominations={"d50": 5}),
            "received",
        )
        self.assertEqual(
            presenter.dispute_cash_handover(handover_id="handover-1", reason="Diferencia"),
            "disputed",
        )
        self.assertEqual([name for name, _ in calls], ["deliver", "receive", "dispute"])
        self.assertEqual(calls[0][1]["branch_id"], "branch-1")
        self.assertEqual(calls[1][1]["actor_user_id"], "user-1")
        self.assertEqual(calls[2][1]["reason"], "Diferencia")

    def test_presenter_executes_cash_refund_with_injected_handler(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={"execute_cash_refund": lambda **kwargs: calls.append(kwargs) or "refund"},
        )

        self.assertEqual(
            presenter.execute_cash_refund(
                refund_id="refund-1",
                sale_id="sale-1",
                authorized_by="supervisor-1",
                original_payment_lines={"CASH": Decimal("100.00")},
                refund_lines={"CASH": Decimal("40.00")},
                reason="Devolucion autorizada",
            ),
            "refund",
        )
        self.assertEqual(calls[0]["branch_id"], "branch-1")
        self.assertEqual(calls[0]["cashier_user_id"], "user-1")
        self.assertEqual(calls[0]["authorized_by"], "supervisor-1")
        self.assertEqual(calls[0]["refund_lines"], {"CASH": Decimal("40.00")})

    def test_presenter_difference_workflow_commands(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "explain_cash_difference": lambda **kwargs: calls.append(("explain", kwargs)) or "explained",
                "review_cash_difference": lambda **kwargs: calls.append(("review", kwargs)) or "reviewed",
                "resolve_cash_difference": lambda **kwargs: calls.append(("resolve", kwargs)) or "resolved",
            },
        )

        self.assertEqual(
            presenter.explain_cash_difference(difference_id="diff-1", explanation="Faltante explicado"),
            "explained",
        )
        self.assertEqual(presenter.review_cash_difference(difference_id="diff-1"), "reviewed")
        self.assertEqual(
            presenter.resolve_cash_difference(difference_id="diff-1", resolution="Reposicion documentada"),
            "resolved",
        )
        self.assertEqual([name for name, _ in calls], ["explain", "review", "resolve"])
        self.assertEqual(calls[0][1]["branch_id"], "branch-1")
        self.assertEqual(calls[1][1]["actor_user_id"], "user-1")
        self.assertEqual(calls[2][1]["resolution"], "Reposicion documentada")

    def test_presenter_z_cut_workflow_commands(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "generate_z_cut": lambda **kwargs: calls.append(("generate", kwargs)) or "z-cut",
                "print_z_cut": lambda **kwargs: calls.append(("print", kwargs)) or "print-id",
                "notify_z_cut": lambda **kwargs: calls.append(("notify", kwargs)) or "notified",
            },
            active_context_provider=lambda: {"cash_shift_id": "shift-1"},
        )

        self.assertEqual(presenter.generate_z_cut(), "z-cut")
        self.assertEqual(
            presenter.print_z_cut(
                cut_id="cut-1",
                reprint=True,
                original_print_id="print-1",
                reprint_reason="Papel dañado",
            ),
            "print-id",
        )
        self.assertEqual(presenter.notify_z_cut(cut_id="cut-1"), "notified")
        self.assertEqual([name for name, _ in calls], ["generate", "print", "notify"])
        self.assertEqual(calls[0][1]["shift_id"], "shift-1")
        self.assertEqual(calls[0][1]["branch_id"], "branch-1")
        self.assertEqual(calls[1][1]["reprint"], True)
        self.assertEqual(calls[1][1]["reprint_reason"], "Papel dañado")
        self.assertEqual(calls[2][1]["actor_user_id"], "user-1")

    def test_presenter_x_cut_workflow_commands(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "generate_x_cut": lambda **kwargs: calls.append(("generate", kwargs)) or "x-cut",
                "print_x_cut": lambda **kwargs: calls.append(("print", kwargs)) or "print-id",
            },
            active_context_provider=lambda: {"cash_shift_id": "shift-1"},
        )

        self.assertEqual(presenter.generate_x_cut(), "x-cut")
        self.assertEqual(
            presenter.print_x_cut(
                cut_id="cut-1",
                reprint=True,
                original_print_id="print-1",
                reprint_reason="Ticket ilegible",
            ),
            "print-id",
        )
        self.assertEqual([name for name, _ in calls], ["generate", "print"])
        self.assertEqual(calls[0][1]["shift_id"], "shift-1")
        self.assertEqual(calls[0][1]["branch_id"], "branch-1")
        self.assertEqual(calls[1][1]["reprint"], True)
        self.assertEqual(calls[1][1]["reprint_reason"], "Ticket ilegible")

    def test_presenter_cash_hardware_commands(self):
        calls = []
        presenter = CashRegisterPresenter(
            session_context=_Session(),
            command_handlers={
                "create_cash_device": lambda **kwargs: calls.append(("create", kwargs)) or "created",
                "set_cash_device_status": lambda **kwargs: calls.append(("status", kwargs)) or "updated",
                "diagnose_cash_hardware": lambda **kwargs: calls.append(("diagnose", kwargs)) or "diagnostic",
                "open_cash_drawer_hardware": lambda **kwargs: calls.append(("open", kwargs)) or "opened",
            },
        )

        self.assertEqual(
            presenter.create_cash_device(kind="register", name="Caja 1"),
            "created",
        )
        self.assertEqual(
            presenter.set_cash_device_status(
                kind="drawer", device_id="drawer-1", activate=False, reason="Mantenimiento"),
            "updated",
        )
        self.assertEqual(presenter.diagnose_cash_hardware(device_id="drawer-1"), "diagnostic")
        self.assertEqual(
            presenter.open_cash_drawer_hardware(drawer_id="drawer-1", reason="Prueba auditada"),
            "opened",
        )
        self.assertEqual([name for name, _ in calls], ["create", "status", "diagnose", "open"])
        self.assertEqual(calls[0][1]["branch_id"], "branch-1")
        self.assertEqual(calls[0][1]["actor_user_id"], "user-1")
        self.assertEqual(calls[1][1]["reason"], "Mantenimiento")
        self.assertEqual(calls[2][1]["device_id"], "drawer-1")
        self.assertEqual(calls[3][1]["reason"], "Prueba auditada")

    def test_presenter_sync_commands_require_explicit_device_context(self):
        calls = []

        class _SyncQuery:
            def get(self, **kwargs):
                calls.append(("state", kwargs))
                return {"sync_status": "IDLE", "connectivity": "ONLINE"}

            def list_envelopes(self, **kwargs):
                calls.append(("envelopes", kwargs))
                return [{"id": "env-1"}]

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            query_services={"sync": _SyncQuery()},
            command_handlers={
                "run_cash_sync_cycle": lambda **kwargs: calls.append(("run", kwargs)) or "cycle",
                "set_cash_sync_connectivity": (
                    lambda **kwargs: calls.append(("connectivity", kwargs)) or "online"
                ),
                "resolve_cash_sync_conflict": (
                    lambda **kwargs: calls.append(("resolve", kwargs)) or "resolved"
                ),
            },
            active_context_provider=lambda: {"sync_device_id": "device-1"},
        )

        self.assertEqual(presenter.cash_sync_state()["sync_status"], "IDLE")
        self.assertEqual(presenter.cash_sync_records(), [{"id": "env-1"}])
        self.assertEqual(presenter.run_cash_sync_cycle(), "cycle")
        self.assertEqual(presenter.set_cash_sync_connectivity(online=False), "online")
        self.assertEqual(
            presenter.resolve_cash_sync_conflict(
                envelope_id="env-1",
                strategy="RETRY_LOCAL",
                reason="Preferir evento local auditado",
            ),
            "resolved",
        )
        self.assertEqual([name for name, _ in calls],
                         ["state", "envelopes", "run", "connectivity", "resolve"])
        self.assertEqual(calls[0][1]["device_id"], "device-1")
        self.assertEqual(calls[2][1]["branch_id"], "branch-1")
        self.assertEqual(calls[3][1]["online"], False)
        self.assertEqual(calls[4][1]["reason"], "Preferir evento local auditado")

        missing_context = CashRegisterPresenter(
            session_context=_Session(),
            query_services={"sync": _SyncQuery()},
        )
        with self.assertRaises(CashContextError):
            missing_context.cash_sync_state()

    def test_presenter_notification_queries_and_dispatch_use_injected_services(self):
        calls = []

        class _Notifications:
            def dashboard(self, **kwargs):
                calls.append(("dashboard", kwargs))
                return {"unread": 2, "pending": 1}

            def unread(self, **kwargs):
                calls.append(("alerts", kwargs))
                return [{"id": "alert-1"}]

            def recent_jobs(self, **kwargs):
                calls.append(("jobs", kwargs))
                return [{"id": "job-1"}]

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            query_services={"notifications": _Notifications()},
            command_handlers={
                "dispatch_cash_notifications": (
                    lambda **kwargs: calls.append(("dispatch", kwargs)) or "sent"
                )
            },
        )

        self.assertEqual(presenter.cash_notifications_dashboard()["unread"], 2)
        self.assertEqual(presenter.cash_notification_alerts(), [{"id": "alert-1"}])
        self.assertEqual(presenter.cash_notification_jobs(), [{"id": "job-1"}])
        self.assertEqual(presenter.dispatch_cash_notifications(), "sent")
        self.assertEqual([name for name, _ in calls],
                         ["dashboard", "alerts", "jobs", "dispatch"])
        self.assertEqual(calls[0][1]["branch_id"], "branch-1")
        self.assertEqual(calls[3][1]["actor_user_id"], "user-1")

    def test_presenter_overview_uses_injected_query_service(self):
        calls = []

        class _Overview:
            def dashboard(self, **kwargs):
                calls.append(kwargs)
                return "overview"

        presenter = CashRegisterPresenter(
            session_context=_Session(),
            query_services={"overview": _Overview()},
        )

        self.assertEqual(presenter.cash_overview_dashboard(), "overview")
        self.assertEqual(calls[0]["branch_id"], "branch-1")
        self.assertEqual(calls[0]["requester_user_id"], "user-1")


if __name__ == "__main__":
    unittest.main()
