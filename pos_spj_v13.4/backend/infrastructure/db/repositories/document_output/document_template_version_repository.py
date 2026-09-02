"""SqliteDocumentTemplateVersionRepository — persists `DocumentTemplateVersion`
(SET-11). Implements
`backend.domain.document_output.repository_ports.DocumentTemplateVersionRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.enums import DocumentTemplateVersionStatus, RenderFormat
from backend.infrastructure.db.repositories.document_output.base import DocumentOutputRepositoryBase

_COLS = (
    "id, template_id, version, content_format, content, status, created_by_user_id,"
    " approved_by_user_id, activated_by_user_id, reason, previous_version_id, created_at, updated_at"
)


class SqliteDocumentTemplateVersionRepository(DocumentOutputRepositoryBase):
    def save(self, version: DocumentTemplateVersion) -> None:
        self._execute(
            f"INSERT INTO document_template_versions ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " status=excluded.status, approved_by_user_id=excluded.approved_by_user_id,"
            " activated_by_user_id=excluded.activated_by_user_id, reason=excluded.reason,"
            " updated_at=excluded.updated_at",
            self._params(version),
        )

    def get(self, version_id: str) -> DocumentTemplateVersion | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM document_template_versions WHERE id=?", (version_id,),
        )
        return self._hydrate(row) if row else None

    def list_for_template(self, template_id: str) -> list[DocumentTemplateVersion]:
        rows = self._query(
            f"SELECT {_COLS} FROM document_template_versions WHERE template_id=? ORDER BY version",
            (template_id,),
        )
        return [self._hydrate(row) for row in rows]

    def get_active_for_template(self, template_id: str) -> DocumentTemplateVersion | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM document_template_versions WHERE template_id=? AND status='ACTIVE'",
            (template_id,),
        )
        return self._hydrate(row) if row else None

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(version: DocumentTemplateVersion) -> tuple:
        return (
            version.id, version.template_id, version.version, version.content_format.value,
            version.content, version.status.value, version.created_by_user_id,
            version.approved_by_user_id, version.activated_by_user_id, version.reason,
            version.previous_version_id, version.created_at, version.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DocumentTemplateVersion:
        return DocumentTemplateVersion(
            id=row["id"], template_id=row["template_id"], version=row["version"],
            content_format=RenderFormat(row["content_format"]), content=row["content"],
            status=DocumentTemplateVersionStatus(row["status"]),
            created_by_user_id=row["created_by_user_id"], approved_by_user_id=row["approved_by_user_id"],
            activated_by_user_id=row["activated_by_user_id"], reason=row["reason"],
            previous_version_id=row["previous_version_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
