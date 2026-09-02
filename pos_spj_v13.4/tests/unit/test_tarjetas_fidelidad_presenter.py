"""LOY-25 — TarjetasFidelidadPresenter unit tests (fake command handlers/
query services, no live connection)."""

from __future__ import annotations

from backend.application.loyalty_cards.result import LoyaltyCardResult
from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_presenter import (
    TarjetasFidelidadPresenter,
)
from frontend.desktop.modules.tarjetas_fidelidad.view_models import (
    TarjetasFidelidadCapabilities,
)


class _FakeSession:
    user_id = "u1"
    active_branch_id = "b1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class TestCapabilities:
    def test_all_true_when_session_grants_everything(self):
        presenter = TarjetasFidelidadPresenter(session_context=_FakeSession())
        caps = presenter.capabilities()
        assert isinstance(caps, TarjetasFidelidadCapabilities)
        assert caps.module_view is True
        assert caps.cards is True


class TestUnwiredDegradesGracefully:
    def test_find_card_by_number_returns_none(self):
        presenter = TarjetasFidelidadPresenter(session_context=_FakeSession())
        assert presenter.find_card_by_number("LC-00000001") is None

    def test_issue_card_returns_not_wired(self):
        presenter = TarjetasFidelidadPresenter(session_context=_FakeSession())
        result = presenter.issue_card(customer_id="c1", membership_id="m1")
        assert not result.success
        assert result.error_code == "NOT_WIRED"


class TestCommandHandlersReceiveExpectedArgs:
    def test_issue_card_calls_handler_with_actor_and_branch(self):
        captured = {}

        def fake_handler(**kwargs):
            captured.update(kwargs)
            return LoyaltyCardResult.ok("Tarjeta emitida", entity_id="card-1")

        presenter = TarjetasFidelidadPresenter(
            session_context=_FakeSession(), command_handlers={"issue_card": fake_handler})
        result = presenter.issue_card(customer_id="c1", membership_id="m1")

        assert result.success
        assert captured["customer_id"] == "c1"
        assert captured["actor_user_id"] == "u1"
        assert captured["actor_branch_id"] == "b1"

    def test_block_card_passes_reason(self):
        captured = {}

        def fake_handler(**kwargs):
            captured.update(kwargs)
            return LoyaltyCardResult.ok("Tarjeta bloqueada")

        presenter = TarjetasFidelidadPresenter(
            session_context=_FakeSession(), command_handlers={"block_card": fake_handler})
        presenter.block_card(card_id="card-1", reason="reportada perdida")

        assert captured["card_id"] == "card-1"
        assert captured["reason"] == "reportada perdida"
