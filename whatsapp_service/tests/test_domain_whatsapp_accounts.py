# tests/test_domain_whatsapp_accounts.py — WA-2
"""WhatsAppBusinessAccount / WhatsAppProviderConfiguration."""
from __future__ import annotations

import pytest

from domain.whatsapp.entities.business_account import (
    WhatsAppBusinessAccount,
    WhatsAppProviderConfiguration,
)
from domain.whatsapp.enums import AccountStatus, WhatsAppProvider


def _account(**overrides):
    defaults = dict(
        provider=WhatsAppProvider.META,
        business_account_external_id="123456",
        display_name="SPJ Carnicería",
    )
    defaults.update(overrides)
    return WhatsAppBusinessAccount.create(**defaults)


class TestWhatsAppBusinessAccountCreate:
    def test_starts_in_draft(self):
        account = _account()
        assert account.status == AccountStatus.DRAFT

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7
        account = _account()
        assert is_uuidv7(account.id)

    def test_two_accounts_have_different_ids(self):
        assert _account().id != _account().id

    def test_rejects_empty_external_id(self):
        with pytest.raises(ValueError):
            _account(business_account_external_id="")

    def test_rejects_blank_display_name(self):
        with pytest.raises(ValueError):
            _account(display_name="   ")

    def test_strips_whitespace(self):
        account = _account(
            business_account_external_id="  999  ", display_name="  Nombre  "
        )
        assert account.business_account_external_id == "999"
        assert account.display_name == "Nombre"


class TestWhatsAppBusinessAccountLifecycle:
    def test_activate_sets_active(self):
        account = _account()
        account.activate()
        assert account.status == AccountStatus.ACTIVE

    def test_activate_bumps_updated_at(self):
        account = _account()
        before = account.updated_at
        account.activate()
        assert account.updated_at >= before

    def test_cannot_activate_retired_account(self):
        account = _account()
        account.retire()
        with pytest.raises(ValueError):
            account.activate()

    def test_cannot_suspend_retired_account(self):
        account = _account()
        account.retire()
        with pytest.raises(ValueError):
            account.suspend()

    def test_is_usable_true_when_active(self):
        account = _account()
        account.activate()
        assert account.is_usable() is True

    def test_is_usable_true_when_degraded(self):
        account = _account()
        account.activate()
        account.mark_degraded()
        assert account.is_usable() is True

    def test_is_usable_false_when_draft(self):
        assert _account().is_usable() is False

    def test_is_usable_false_when_suspended(self):
        account = _account()
        account.activate()
        account.suspend()
        assert account.is_usable() is False


class TestWhatsAppProviderConfiguration:
    def test_create_requires_account_id(self):
        with pytest.raises(ValueError):
            WhatsAppProviderConfiguration.create(
                account_id="", provider=WhatsAppProvider.META, api_version="v21.0"
            )

    def test_create_requires_api_version(self):
        with pytest.raises(ValueError):
            WhatsAppProviderConfiguration.create(
                account_id="acc-1", provider=WhatsAppProvider.META, api_version=""
            )

    def test_extra_settings_defaults_to_empty_dict(self):
        config = WhatsAppProviderConfiguration.create(
            account_id="acc-1", provider=WhatsAppProvider.META, api_version="v21.0"
        )
        assert config.extra_settings == {}

    def test_extra_settings_is_copied_not_aliased(self):
        source = {"a": 1}
        config = WhatsAppProviderConfiguration.create(
            account_id="acc-1",
            provider=WhatsAppProvider.META,
            api_version="v21.0",
            extra_settings=source,
        )
        source["a"] = 999
        assert config.extra_settings["a"] == 1
