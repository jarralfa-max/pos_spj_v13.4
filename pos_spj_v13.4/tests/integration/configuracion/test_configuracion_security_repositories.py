"""SET-1 — configuracion_authorization_log / configuracion_audit_log
persistence (migration 224). Against a real (in-memory) SQLite born-clean
schema, mirroring `test_configuracion_company_branch_use_cases.py`'s
fixture shape.
"""

from __future__ import annotations

import pytest

from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.domain.settings.value_objects.authorization_grant import AuthorizationGrant
from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
    ConfiguracionAuditLogRepository,
    ConfiguracionAuthorizationLogRepository,
)
from backend.shared.ids import is_uuidv7, new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestConfiguracionAuthorizationLogRepository:
    def test_records_and_lists_by_operation(self, conn):
        repo = ConfiguracionAuthorizationLogRepository(conn)
        operation_id = new_uuid()
        grant = AuthorizationGrant(
            permission_code="DOCUMENTOS.plantilla.aprobar", requested_by="editor-1",
            authorized_by="reviewer-2", operation_id=operation_id, reason="Aprobación de plantilla fiscal",
        )
        row_id = repo.record(grant)
        conn.commit()

        assert is_uuidv7(row_id)
        rows = repo.list_for_operation(operation_id)
        assert len(rows) == 1
        assert rows[0]["requested_by"] == "editor-1"
        assert rows[0]["authorized_by"] == "reviewer-2"
        assert rows[0]["permission_code"] == "DOCUMENTOS.plantilla.aprobar"
        assert rows[0]["reason"] == "Aprobación de plantilla fiscal"

    def test_list_for_unknown_operation_is_empty(self, conn):
        repo = ConfiguracionAuthorizationLogRepository(conn)
        assert repo.list_for_operation(new_uuid()) == []


class TestConfiguracionAuditLogRepository:
    def test_records_and_lists_before_after_for_entity(self, conn):
        repo = ConfiguracionAuditLogRepository(conn)
        device_id = new_uuid()
        repo.record(
            entity_type="device", entity_id=device_id, action="BLOCK",
            user_id="admin-1", before_json='{"status": "ACTIVE"}',
            after_json='{"status": "BLOCKED"}', reason="Sospecha de manipulación",
        )
        conn.commit()

        rows = repo.list_for_entity("device", device_id)
        assert len(rows) == 1
        assert rows[0]["action"] == "BLOCK"
        assert rows[0]["before_json"] == '{"status": "ACTIVE"}'
        assert rows[0]["after_json"] == '{"status": "BLOCKED"}'
        assert rows[0]["source_module"] == "configuracion"

    def test_list_for_unknown_entity_is_empty(self, conn):
        repo = ConfiguracionAuditLogRepository(conn)
        assert repo.list_for_entity("device", new_uuid()) == []
