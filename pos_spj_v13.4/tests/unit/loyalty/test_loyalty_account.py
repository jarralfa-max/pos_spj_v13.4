"""LOY-2 — LoyaltyAccount lifecycle (master prompt §10)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.enums import AccountStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyAccountStateError
from backend.shared.ids import new_uuid


class TestLoyaltyAccount:
    def test_create_defaults_to_active(self):
        account = LoyaltyAccount.create(new_uuid())
        assert account.status is AccountStatus.ACTIVE
        assert account.is_operational() is True

    def test_requires_customer_id(self):
        with pytest.raises(InvalidLoyaltyAccountStateError):
            LoyaltyAccount.create("")

    def test_never_duplicates_customer_fields(self):
        """Master prompt §4/§52: LoyaltyAccount only references customer_id,
        never name/phone/email."""
        account = LoyaltyAccount.create(new_uuid())
        fields = {f for f in account.__slots__}
        assert "customer_id" in fields
        assert not ({"name", "phone", "email", "display_name"} & fields)

    def test_suspend_and_reactivate(self):
        account = LoyaltyAccount.create(new_uuid())
        account.suspend("Fraude sospechado")
        assert account.status is AccountStatus.SUSPENDED
        account.reactivate()
        assert account.status is AccountStatus.ACTIVE

    def test_suspend_requires_reason(self):
        account = LoyaltyAccount.create(new_uuid())
        with pytest.raises(InvalidLoyaltyAccountStateError):
            account.suspend("")

    def test_close_is_terminal(self):
        account = LoyaltyAccount.create(new_uuid())
        account.close("Cliente solicitó cierre")
        assert account.status is AccountStatus.CLOSED
        with pytest.raises(InvalidLoyaltyAccountStateError):
            account.close("de nuevo")
