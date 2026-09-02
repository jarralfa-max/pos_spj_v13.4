"""LOY-25 — FidelidadPresenter unit tests (fake command handlers/query
services, no live connection — mirrors
``tests/unit/test_customers_crm_create_customer_page.py``'s presenter
testing style)."""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.queries.member_profile_query_service import (
    LoyaltyMemberProfileView,
)
from backend.application.loyalty.result import LoyaltyResult
from frontend.desktop.modules.fidelidad.fidelidad_presenter import FidelidadPresenter
from frontend.desktop.modules.fidelidad.view_models import FidelidadCapabilities


class _FakeSession:
    user_id = "u1"
    active_branch_id = "b1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class TestCapabilities:
    def test_all_true_when_session_grants_everything(self):
        presenter = FidelidadPresenter(session_context=_FakeSession())
        caps = presenter.capabilities()
        assert isinstance(caps, FidelidadCapabilities)
        assert caps.module_view is True
        assert caps.programs is True
        assert caps.sweepstakes is True

    def test_all_false_without_a_session(self):
        presenter = FidelidadPresenter(session_context=None)
        caps = presenter.capabilities()
        assert caps.module_view is False


class TestUnwiredDegradesGracefully:
    def test_list_programs_returns_empty_list(self):
        presenter = FidelidadPresenter(session_context=_FakeSession())
        assert presenter.list_programs() == []

    def test_create_program_returns_not_wired(self):
        presenter = FidelidadPresenter(session_context=_FakeSession())
        result = presenter.create_program(code="X", name="Y", currency_name="Z")
        assert not result.success
        assert result.error_code == "NOT_WIRED"

    def test_member_profile_returns_not_found_view(self):
        presenter = FidelidadPresenter(session_context=_FakeSession())
        view = presenter.member_profile("customer-1")
        assert isinstance(view, LoyaltyMemberProfileView)
        assert view.found is False


class TestCommandHandlersReceiveExpectedArgs:
    def test_create_program_calls_handler_with_actor_and_operation_id(self):
        captured = {}

        def fake_handler(**kwargs):
            captured.update(kwargs)
            return LoyaltyResult.ok("Programa creado", entity_id="p1")

        presenter = FidelidadPresenter(
            session_context=_FakeSession(),
            command_handlers={"create_program": fake_handler})
        result = presenter.create_program(code="PTS", name="Puntos", currency_name="Estrellas")

        assert result.success
        assert captured["code"] == "PTS"
        assert captured["actor_user_id"] == "u1"
        assert captured["actor_branch_id"] == "b1"
        assert "operation_id" in captured

    def test_accrue_points_calls_handler_with_decimal_amount(self):
        captured = {}

        def fake_handler(**kwargs):
            captured.update(kwargs)
            return LoyaltyResult.ok("Puntos acreditados")

        presenter = FidelidadPresenter(
            session_context=_FakeSession(),
            command_handlers={"accrue_points": fake_handler})
        presenter.accrue_points(
            loyalty_account_id="acc-1", points_amount=Decimal("100"), reason_code="Bono")

        assert captured["loyalty_account_id"] == "acc-1"
        assert captured["points_amount"] == Decimal("100")
        assert captured["source_module"] == "fidelidad_ui"

    def test_redeem_reward_requests_then_confirms(self):
        calls = []

        def fake_request(**kwargs):
            calls.append(("request", kwargs))
            return LoyaltyResult.ok("Canje reservado", entity_id="redemption-1")

        def fake_confirm(**kwargs):
            calls.append(("confirm", kwargs))
            return LoyaltyResult.ok("Canje confirmado")

        presenter = FidelidadPresenter(
            session_context=_FakeSession(),
            command_handlers={
                "request_reward_redemption": fake_request,
                "confirm_reward_redemption": fake_confirm,
            })
        result = presenter.redeem_reward(reward_id="reward-1", membership_id="membership-1")

        assert result.success
        assert calls[0][0] == "request"
        assert calls[1][0] == "confirm"
        assert calls[1][1]["redemption_id"] == "redemption-1"

    def test_redeem_reward_does_not_confirm_when_request_fails(self):
        calls = []

        def fake_request(**kwargs):
            calls.append("request")
            return LoyaltyResult.fail("Saldo insuficiente", "INSUFFICIENT_POINTS")

        def fake_confirm(**kwargs):
            calls.append("confirm")
            return LoyaltyResult.ok("no debería llamarse")

        presenter = FidelidadPresenter(
            session_context=_FakeSession(),
            command_handlers={
                "request_reward_redemption": fake_request,
                "confirm_reward_redemption": fake_confirm,
            })
        result = presenter.redeem_reward(reward_id="reward-1", membership_id="membership-1")

        assert not result.success
        assert calls == ["request"]
