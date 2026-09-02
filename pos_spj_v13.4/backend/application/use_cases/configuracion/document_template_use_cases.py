"""Use cases for the "Documentos" section of the Configuración
workspace — second section with real CRUD (SET-25 follow-up #3). Thin
orchestration over `backend/domain/document_output/` (SET-11): construct
the entities, apply the domain's own 7-state transition rules, persist.

`ChangeTemplateVersionStatusUseCase` is deliberately ONE use case for all
7 transitions (submit/approve/reject/activate/deactivate/expire/archive)
— same "one class, many actions" shape as
`device_management_use_cases.py::ChangeDeviceStatusUseCase`. `ACTIVATE`
deactivates the template's current active version first (if any and
different) so activating a replacement version never trips over an
already-active one — same ordering fix already applied to
`SetDefaultThemeUseCase` (SET-22/25): unmark the old one before marking
the new one, never assume it's already clear.

SET-11 follow-up: `DocumentTemplate.activate()`/`deactivate()` (the
whole *family*, not one version) existed since the original cut but
were never wired to a use case at all — no way to retire a template
family entirely (e.g. "we no longer print gift receipts"), distinct
from deactivating a single version's content.
`UpdateDocumentTemplateUseCase`/`ChangeDocumentTemplateStatusUseCase`
close that gap, and `DocumentTemplate.update_details()` (also new) is
the first way to rename/redescribe a template family after creation.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.enums import DocumentType, RenderFormat
from backend.domain.document_output.exceptions import (
    DocumentTemplateNotFoundError,
    TemplateVersionNotFoundError,
)
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)


class TemplateVersionAction(str, Enum):
    SUBMIT_FOR_APPROVAL = "SUBMIT_FOR_APPROVAL"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"
    EXPIRE = "EXPIRE"
    ARCHIVE = "ARCHIVE"


class DocumentTemplateStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class CreateDocumentTemplateUseCase:
    """Creates a `DocumentTemplate` family together with its first
    (DRAFT) `DocumentTemplateVersion` — a template with zero versions
    isn't useful, so the UI's "new template" action always produces both."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._templates = SqliteDocumentTemplateRepository(connection)
        self._versions = SqliteDocumentTemplateVersionRepository(connection)

    def execute(
        self, *, document_type: DocumentType | str, name: str, module: str, description: str = "",
        content_format: RenderFormat | str, content: str, created_by_user_id: str = "",
    ) -> tuple[DocumentTemplate, DocumentTemplateVersion]:
        template = DocumentTemplate.create(
            document_type=DocumentType(document_type), name=name, module=module, description=description,
        )
        version = DocumentTemplateVersion.create(
            template_id=template.id, content_format=RenderFormat(content_format), content=content,
            created_by_user_id=created_by_user_id or None,
        )
        self._templates.save(template)
        self._versions.save(version)
        self._conn.commit()
        return template, version


class CreateNextTemplateVersionUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._versions = SqliteDocumentTemplateVersionRepository(connection)

    def execute(
        self, *, version_id: str, content: str, created_by_user_id: str = "",
    ) -> DocumentTemplateVersion:
        current = self._versions.get(version_id)
        if current is None:
            raise TemplateVersionNotFoundError(f"Versión {version_id} no encontrada")
        next_version = current.create_next_version(content=content, created_by_user_id=created_by_user_id or None)
        self._versions.save(next_version)
        self._conn.commit()
        return next_version


class ChangeTemplateVersionStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._versions = SqliteDocumentTemplateVersionRepository(connection)

    def execute(
        self, *, version_id: str, action: TemplateVersionAction, actor_user_id: str = "", reason: str = "",
    ) -> DocumentTemplateVersion:
        version = self._versions.get(version_id)
        if version is None:
            raise TemplateVersionNotFoundError(f"Versión {version_id} no encontrada")

        if action is TemplateVersionAction.SUBMIT_FOR_APPROVAL:
            version.submit_for_approval()
        elif action is TemplateVersionAction.APPROVE:
            version.approve(actor_user_id)
        elif action is TemplateVersionAction.REJECT:
            version.reject(reason)
        elif action is TemplateVersionAction.ACTIVATE:
            current_active = self._versions.get_active_for_template(version.template_id)
            if current_active is not None and current_active.id != version.id:
                current_active.deactivate()
                self._versions.save(current_active)
            version.activate(actor_user_id)
        elif action is TemplateVersionAction.DEACTIVATE:
            version.deactivate()
        elif action is TemplateVersionAction.EXPIRE:
            version.expire()
        elif action is TemplateVersionAction.ARCHIVE:
            version.archive()

        self._versions.save(version)
        self._conn.commit()
        return version


class UpdateDocumentTemplateUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._templates = SqliteDocumentTemplateRepository(connection)

    def execute(self, *, template_id: str, name: str, module: str, description: str = "") -> DocumentTemplate:
        template = self._templates.get(template_id)
        if template is None:
            raise DocumentTemplateNotFoundError(f"Plantilla {template_id} no encontrada")
        template.update_details(name=name, module=module, description=description)
        self._templates.save(template)
        self._conn.commit()
        return template


class ChangeDocumentTemplateStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._templates = SqliteDocumentTemplateRepository(connection)

    def execute(self, *, template_id: str, action: DocumentTemplateStatusAction) -> DocumentTemplate:
        template = self._templates.get(template_id)
        if template is None:
            raise DocumentTemplateNotFoundError(f"Plantilla {template_id} no encontrada")

        if action is DocumentTemplateStatusAction.ACTIVATE:
            template.activate()
        elif action is DocumentTemplateStatusAction.DEACTIVATE:
            template.deactivate()

        self._templates.save(template)
        self._conn.commit()
        return template
