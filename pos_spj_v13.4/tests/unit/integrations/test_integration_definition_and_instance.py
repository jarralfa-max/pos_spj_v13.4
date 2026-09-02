"""SET-19 — "Definitions"/"Instances"/"Credentials": IntegrationDefinition,
IntegrationInstance, credential_provisioning_policy. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.enums import IntegrationCategory
from backend.domain.integrations.exceptions import IntegrationsInvalidValueError, MissingCredentialError
from backend.domain.integrations.policies.credential_provisioning_policy import assert_credentials_satisfied
from backend.shared.ids import is_uuidv7, new_uuid


def _definition(**overrides) -> IntegrationDefinition:
    kwargs = dict(
        code="whatsapp", name="WhatsApp Business", category=IntegrationCategory.MESSAGING,
        required_credential_names=["app_secret", "access_token"],
    )
    kwargs.update(overrides)
    return IntegrationDefinition.create(**kwargs)


def _instance(definition_id: str | None = None, **overrides) -> IntegrationInstance:
    kwargs = dict(definition_id=definition_id or new_uuid(), name="Número principal")
    kwargs.update(overrides)
    return IntegrationInstance.create(**kwargs)


class TestIntegrationDefinitionCreate:
    def test_mints_uuidv7_and_normalizes_code(self):
        definition = _definition(code="  whatsapp  ")
        assert is_uuidv7(definition.id)
        assert definition.code == "WHATSAPP"
        assert definition.active is True

    def test_requires_code(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _definition(code="   ")

    def test_requires_name(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _definition(name="   ")

    def test_rejects_duplicate_required_credential_names(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _definition(required_credential_names=["app_secret", "app_secret"])

    def test_defaults_to_no_required_credentials(self):
        definition = IntegrationDefinition.create(
            code="maps", name="Maps", category=IntegrationCategory.LOCATION,
        )
        assert definition.required_credential_names == ()

    def test_activate_deactivate(self):
        definition = _definition()
        definition.deactivate()
        assert definition.active is False
        definition.activate()
        assert definition.active is True


class TestIntegrationDefinitionUpdateDetails:
    def test_updates_name_and_required_credential_names(self):
        definition = _definition()
        definition.update_details(name="WhatsApp Business API", required_credential_names=["access_token"])
        assert definition.name == "WhatsApp Business API"
        assert definition.required_credential_names == ("access_token",)

    def test_requires_name(self):
        definition = _definition()
        with pytest.raises(IntegrationsInvalidValueError):
            definition.update_details(name="   ")

    def test_rejects_duplicate_required_credential_names(self):
        definition = _definition()
        with pytest.raises(IntegrationsInvalidValueError):
            definition.update_details(name="X", required_credential_names=["a", "a"])


class TestIntegrationInstanceCreate:
    def test_mints_uuidv7(self):
        instance = _instance()
        assert is_uuidv7(instance.id)
        assert instance.active is True
        assert instance.config == {}
        assert instance.credential_references == {}

    def test_validates_definition_id_as_uuid(self):
        with pytest.raises(ValueError):
            _instance(definition_id="not-a-uuid")

    def test_requires_name(self):
        with pytest.raises(IntegrationsInvalidValueError):
            _instance(name="   ")

    @pytest.mark.parametrize(
        "key", ["password", "api_key", "apikey", "secret", "access_token", "AUTH_HEADER", "Private_Key"],
    )
    def test_rejects_secret_like_config_keys(self, key):
        with pytest.raises(IntegrationsInvalidValueError):
            _instance(config={key: "raw-value"})

    def test_accepts_non_secret_config_keys(self):
        instance = _instance(config={"phone_number_id": "123"})
        assert instance.config == {"phone_number_id": "123"}

    def test_activate_deactivate(self):
        instance = _instance()
        instance.deactivate()
        assert instance.active is False
        instance.activate()
        assert instance.active is True

    def test_set_credential_reference(self):
        instance = _instance()
        instance.set_credential_reference("app_secret", "whatsapp/app_secret")
        assert instance.credential_references == {"app_secret": "whatsapp/app_secret"}


class TestIntegrationInstanceUpdateDetails:
    def test_updates_name_and_config(self):
        instance = _instance()
        instance.update_details(name="Número secundario", config={"phone_number_id": "456"})
        assert instance.name == "Número secundario"
        assert instance.config == {"phone_number_id": "456"}

    def test_requires_name(self):
        instance = _instance()
        with pytest.raises(IntegrationsInvalidValueError):
            instance.update_details(name="   ")

    def test_rejects_secret_like_config_keys(self):
        instance = _instance()
        with pytest.raises(IntegrationsInvalidValueError):
            instance.update_details(name="X", config={"password": "raw"})


class TestAssertCredentialsSatisfied:
    def test_missing_credential_raises(self):
        definition = _definition()
        instance = _instance(definition_id=definition.id)
        with pytest.raises(MissingCredentialError):
            assert_credentials_satisfied(definition, instance)

    def test_partial_credentials_still_raises(self):
        definition = _definition()
        instance = _instance(definition_id=definition.id)
        instance.set_credential_reference("app_secret", "whatsapp/app_secret")
        with pytest.raises(MissingCredentialError):
            assert_credentials_satisfied(definition, instance)

    def test_all_credentials_present_does_not_raise(self):
        definition = _definition()
        instance = _instance(definition_id=definition.id)
        instance.set_credential_reference("app_secret", "whatsapp/app_secret")
        instance.set_credential_reference("access_token", "whatsapp/access_token")
        assert_credentials_satisfied(definition, instance)  # does not raise

    def test_definition_with_no_requirements_never_raises(self):
        definition = IntegrationDefinition.create(
            code="maps", name="Maps", category=IntegrationCategory.LOCATION,
        )
        instance = _instance(definition_id=definition.id)
        assert_credentials_satisfied(definition, instance)  # does not raise

    def test_empty_string_reference_counts_as_missing(self):
        definition = _definition()
        instance = _instance(definition_id=definition.id)
        instance.set_credential_reference("app_secret", "")
        instance.set_credential_reference("access_token", "whatsapp/access_token")
        with pytest.raises(MissingCredentialError):
            assert_credentials_satisfied(definition, instance)
