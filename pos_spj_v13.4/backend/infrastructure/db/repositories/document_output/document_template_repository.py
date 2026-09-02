"""SqliteDocumentTemplateRepository — persists `DocumentTemplate` (SET-11).
Implements
`backend.domain.document_output.repository_ports.DocumentTemplateRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.enums import DocumentType
from backend.infrastructure.db.repositories.document_output.base import DocumentOutputRepositoryBase

_COLS = "id, document_type, name, module, description, active, created_at, updated_at"


class SqliteDocumentTemplateRepository(DocumentOutputRepositoryBase):
    def save(self, template: DocumentTemplate) -> None:
        self._execute(
            f"INSERT INTO document_templates ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, module=excluded.module, description=excluded.description,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(template),
        )

    def get(self, template_id: str) -> DocumentTemplate | None:
        row = self._query_one(f"SELECT {_COLS} FROM document_templates WHERE id=?", (template_id,))
        return self._hydrate(row) if row else None

    def list_by_document_type(self, document_type: DocumentType) -> list[DocumentTemplate]:
        rows = self._query(
            f"SELECT {_COLS} FROM document_templates WHERE document_type=? ORDER BY name",
            (document_type.value,),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[DocumentTemplate]:
        rows = self._query(f"SELECT {_COLS} FROM document_templates WHERE active=1 ORDER BY name")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[DocumentTemplate]:
        rows = self._query(f"SELECT {_COLS} FROM document_templates ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(template: DocumentTemplate) -> tuple:
        return (
            template.id, template.document_type.value, template.name, template.module,
            template.description, int(template.active), template.created_at, template.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DocumentTemplate:
        return DocumentTemplate(
            id=row["id"], document_type=DocumentType(row["document_type"]), name=row["name"],
            module=row["module"], description=row["description"] or "", active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
