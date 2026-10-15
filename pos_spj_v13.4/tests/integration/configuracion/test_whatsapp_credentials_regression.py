"""Stored integration credentials survive restart and channel rotation."""
import sqlite3

import pytest

from backend.application.use_cases.configuracion.integration_management_use_cases import (
    CreateIntegrationDefinitionUseCase, CreateIntegrationInstanceUseCase,
    SetIntegrationInstanceCredentialUseCase,
)
from backend.application.queries.configuracion.workspace_query_service import ConfiguracionWorkspaceQueryService
from backend.domain.integrations.enums import IntegrationCategory
from backend.infrastructure.db.schema.integrations_schema import create_integrations_schema
from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore


@pytest.fixture
def saved_channel(tmp_path):
    path = tmp_path / "erp.db"
    conn = sqlite3.connect(path)
    create_integrations_schema(conn)
    definition = CreateIntegrationDefinitionUseCase(conn).execute(
        code="WHATSAPP", name="WhatsApp", category=IntegrationCategory.MESSAGING,
        required_credential_names=("wa_meta_token", "wa_app_secret"),
    )
    instance = CreateIntegrationInstanceUseCase(conn).execute(definition_id=definition.id, name="Sucursal")
    vault = EncryptedLocalSecretStore(store_dir=tmp_path / "vault")
    yield conn, path, instance, vault, tmp_path
    conn.close()


def test_saved_credential_is_read_by_channel_and_rotation_is_immediate(saved_channel):
    from whatsapp_service.infrastructure.secrets.secret_store import SecretStore
    conn, path, instance, vault, tmp = saved_channel
    read = SecretStore(lambda: str(path), secret_gateway=vault, instance_id=instance.id)
    save = SetIntegrationInstanceCredentialUseCase(conn, vault)
    assert read.get("meta_token", "environment") == ""
    save.execute(instance_id=instance.id, credential_name="wa_meta_token", secret_name="branch-token", secret_value="test-token-one")
    assert read.get("meta_token", "environment") == "test-token-one"
    save.execute(instance_id=instance.id, credential_name="wa_app_secret", secret_name="branch-signature", secret_value="signature-secret")
    save.execute(instance_id=instance.id, credential_name="wa_meta_token", secret_name="branch-token", secret_value="test-token-two")
    assert read.get("meta_token") == "test-token-two"
    assert read.get("app_secret") == "signature-secret"
    restarted = SecretStore(lambda: str(path), secret_gateway=EncryptedLocalSecretStore(store_dir=tmp / "vault"), instance_id=instance.id)
    assert restarted.get("meta_token") == "test-token-two"
    assert "test-token" not in path.read_bytes().decode("utf-8", errors="ignore")
    assert "test-token" not in (tmp / "vault" / "secret_store.enc.json").read_text()


def test_missing_database_is_not_created(tmp_path):
    from whatsapp_service.infrastructure.secrets.secret_store import SecretStore
    path = tmp_path / "typo.db"
    with pytest.raises(RuntimeError, match="database"):
        SecretStore(lambda: str(path)).get("meta_token")
    assert not path.exists()


def test_multiple_instances_require_explicit_scope(saved_channel):
    from whatsapp_service.infrastructure.secrets.secret_store import SecretStore
    conn, path, instance, vault, _ = saved_channel
    CreateIntegrationInstanceUseCase(conn).execute(definition_id=instance.definition_id, name="Otra sucursal")
    with pytest.raises(RuntimeError, match="instance"):
        SecretStore(lambda: str(path), secret_gateway=vault).get("meta_token")


def test_ui_reload_reads_persisted_instance_instead_of_cached_reference(saved_channel):
    from types import SimpleNamespace
    from frontend.desktop.modules.configuracion.pages.integraciones_page import IntegracionesPage
    conn, _, instance, vault, _ = saved_channel
    query = ConfiguracionWorkspaceQueryService(conn, vault)
    presenter = SimpleNamespace(list_integration_instances=query.list_integration_instances,
                                get_credential_status=query.get_credential_status)
    rows = []
    table = SimpleNamespace(load_rows=lambda values, **kw: rows.extend(values), setVisible=lambda _: None)
    page = SimpleNamespace(_selected_instance_id=instance.id, _selected_definition_id=instance.definition_id,
        _instances_by_id={i.entity_id:i for i in query.list_integration_instances(instance.definition_id)},
        _definitions_by_id={instance.definition_id:SimpleNamespace(required_credential_names=("wa_meta_token",))},
        _presenter=presenter, credentials_table=table)
    SetIntegrationInstanceCredentialUseCase(conn, vault).execute(instance_id=instance.id,
        credential_name="wa_meta_token", secret_name="branch-token", secret_value="never-display-this")
    IntegracionesPage._reload_credentials(page)
    assert rows == [["wa_meta_token", "Configurado"]]
    assert "never-display-this" not in str(rows)


def test_short_secret_is_fully_masked():
    from whatsapp_service.infrastructure.secrets.secret_store import SecretStore
    assert "12345678" not in SecretStore.mask("12345678")
