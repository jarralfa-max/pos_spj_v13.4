"""DocumentTemplate — SET-11 (§26): the template *family* for a
document_type (e.g. "the sale ticket template"). Mirrors
`backend/domain/settings/entities/configuration_definition.py`'s role —
mostly-static identity/metadata; the actual versioned content lives in
`DocumentTemplateVersion`, one row per revision (§26: "Toda modificación
crea versión.").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.document_output.enums import DocumentType
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DocumentTemplate:
    id: str
    document_type: DocumentType
    name: str
    module: str
    description: str = ""
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, document_type: DocumentType, name: str, module: str, description: str = "",
    ) -> "DocumentTemplate":
        if not name.strip():
            raise DocumentInvalidValueError("name es obligatorio")
        if not module.strip():
            raise DocumentInvalidValueError("module es obligatorio (el bounded context dueño del contenido, §27)")
        return cls(
            id=new_uuid(), document_type=document_type, name=name.strip(), module=module.strip(),
            description=description.strip(),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(self, *, name: str, module: str, description: str = "") -> None:
        if not name.strip():
            raise DocumentInvalidValueError("name es obligatorio")
        if not module.strip():
            raise DocumentInvalidValueError("module es obligatorio (el bounded context dueño del contenido, §27)")
        self.name = name.strip()
        self.module = module.strip()
        self.description = description.strip()
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
