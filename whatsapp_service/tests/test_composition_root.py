# tests/test_composition_root.py — WA-4
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.composition_root import REQUIRED_SERVICES, WhatsAppCompositionRoot
from bootstrap.dependency_graph_validator import (
    CompositionRootValidationError,
    validate_composition_root,
)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def root(conn):
    return WhatsAppCompositionRoot(conn)


class TestWhatsAppCompositionRoot:
    def test_registers_all_required_services(self, root):
        for name in REQUIRED_SERVICES:
            assert root.registry.has(name)

    def test_validator_passes_on_freshly_built_root(self, root):
        validate_composition_root(root)  # no debe lanzar

    def test_accounts_accessor_returns_working_repository(self, root):
        from domain.whatsapp.entities.business_account import WhatsAppBusinessAccount
        from domain.whatsapp.enums import WhatsAppProvider

        account = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META,
            business_account_external_id="ext-1",
            display_name="SPJ",
        )
        root.accounts.save(account)
        assert root.accounts.get_by_id(account.id) is not None

    def test_numbers_accessor(self, root):
        assert root.numbers is not None

    def test_identities_accessor(self, root):
        assert root.identities is not None

    def test_conversations_accessor(self, root):
        assert root.conversations is not None

    def test_messages_accessor(self, root):
        assert root.messages is not None

    def test_secret_store_accessor_is_the_process_singleton(self, root):
        from config.settings import get_secret_store

        assert root.secret_store is get_secret_store()

    def test_provider_configurations_accessor(self, root):
        assert root.provider_configurations is not None


class TestDependencyGraphValidator:
    def test_raises_when_a_required_service_is_missing(self, conn):
        root = WhatsAppCompositionRoot(conn)
        root.registry._services.pop("whatsapp_message_repository")
        with pytest.raises(CompositionRootValidationError, match="whatsapp_message_repository"):
            validate_composition_root(root)

    def test_error_lists_every_missing_service(self, conn):
        root = WhatsAppCompositionRoot(conn)
        root.registry._services.pop("whatsapp_message_repository")
        root.registry._services.pop("whatsapp_identity_repository")
        with pytest.raises(CompositionRootValidationError) as exc_info:
            validate_composition_root(root)
        assert "whatsapp_message_repository" in str(exc_info.value)
        assert "whatsapp_identity_repository" in str(exc_info.value)
