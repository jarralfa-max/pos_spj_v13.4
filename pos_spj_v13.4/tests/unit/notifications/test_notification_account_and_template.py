"""SET-20 — "Accounts"/"Templates": NotificationAccount,
NotificationTemplate, template_parameter_policy. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.notifications.entities.notification_account import NotificationAccount
from backend.domain.notifications.entities.notification_template import NotificationTemplate
from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.exceptions import (
    NotificationsInvalidValueError,
    TemplateParameterMissingError,
)
from backend.domain.notifications.policies.template_parameter_policy import assert_params_satisfied
from backend.shared.ids import is_uuidv7, new_uuid


def _account(**overrides) -> NotificationAccount:
    kwargs = dict(channel=NotificationChannel.WHATSAPP, name="Número principal")
    kwargs.update(overrides)
    return NotificationAccount.create(**kwargs)


def _template(**overrides) -> NotificationTemplate:
    kwargs = dict(
        code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
        parameter_names=["folio", "total"],
    )
    kwargs.update(overrides)
    return NotificationTemplate.create(**kwargs)


class TestNotificationAccountCreate:
    def test_mints_uuidv7_and_defaults(self):
        account = _account()
        assert is_uuidv7(account.id)
        assert account.active is True
        assert account.integration_instance_id is None

    def test_requires_name(self):
        with pytest.raises(NotificationsInvalidValueError):
            _account(name="   ")

    def test_validates_integration_instance_id_as_uuid_when_present(self):
        with pytest.raises(ValueError):
            _account(integration_instance_id="not-a-uuid")

    def test_accepts_valid_integration_instance_id(self):
        instance_id = new_uuid()
        account = _account(integration_instance_id=instance_id)
        assert account.integration_instance_id == instance_id

    def test_activate_deactivate(self):
        account = _account()
        account.deactivate()
        assert account.active is False
        account.activate()
        assert account.active is True


class TestNotificationAccountUpdateDetails:
    def test_updates_name_and_credential_reference(self):
        account = _account()
        account.update_details(name="Número secundario", credential_reference="wa_secondary_token")
        assert account.name == "Número secundario"
        assert account.credential_reference == "wa_secondary_token"

    def test_requires_name(self):
        account = _account()
        with pytest.raises(NotificationsInvalidValueError):
            account.update_details(name="   ")

    def test_can_clear_credential_reference(self):
        account = _account(credential_reference="wa_token")
        account.update_details(name="X", credential_reference=None)
        assert account.credential_reference is None


class TestNotificationTemplateCreate:
    def test_mints_uuidv7_and_defaults(self):
        template = _template()
        assert is_uuidv7(template.id)
        assert template.active is True

    def test_requires_code(self):
        with pytest.raises(NotificationsInvalidValueError):
            _template(code="   ")

    def test_requires_language(self):
        with pytest.raises(NotificationsInvalidValueError):
            _template(language="   ")

    def test_rejects_duplicate_parameter_names(self):
        with pytest.raises(NotificationsInvalidValueError):
            _template(parameter_names=["folio", "folio"])

    def test_defaults_to_no_parameters(self):
        template = NotificationTemplate.create(
            code="pedido_listo", channel=NotificationChannel.WHATSAPP, language="es_MX",
        )
        assert template.parameter_names == ()

    def test_activate_deactivate(self):
        template = _template()
        template.deactivate()
        assert template.active is False
        template.activate()
        assert template.active is True


class TestNotificationTemplateUpdateParameterNames:
    def test_updates_parameter_names(self):
        template = _template()
        template.update_parameter_names(["folio"])
        assert template.parameter_names == ("folio",)

    def test_can_clear_to_no_parameters(self):
        template = _template()
        template.update_parameter_names([])
        assert template.parameter_names == ()

    def test_rejects_duplicate_parameter_names(self):
        template = _template()
        with pytest.raises(NotificationsInvalidValueError):
            template.update_parameter_names(["a", "a"])


class TestAssertParamsSatisfied:
    def test_all_params_present_does_not_raise(self):
        template = _template()
        assert_params_satisfied(template, {"folio": "VNT-1", "total": "245.00"})

    def test_missing_param_raises(self):
        template = _template()
        with pytest.raises(TemplateParameterMissingError):
            assert_params_satisfied(template, {"folio": "VNT-1"})

    def test_empty_string_param_counts_as_missing(self):
        template = _template()
        with pytest.raises(TemplateParameterMissingError):
            assert_params_satisfied(template, {"folio": "VNT-1", "total": ""})

    def test_no_required_params_never_raises(self):
        template = NotificationTemplate.create(
            code="pedido_listo", channel=NotificationChannel.WHATSAPP, language="es_MX",
        )
        assert_params_satisfied(template, {})
