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
from backend.domain.document_output.enums import (
    LOYALTY_OWNED_DOCUMENT_TYPES,
    DocumentType,
    RenderFormat,
)
from backend.domain.document_output.exceptions import (
    DocumentInvalidValueError,
    DocumentTemplateNotFoundError,
    TemplateVersionNotFoundError,
)
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)



def _configurable(document_type) -> DocumentType:
    """Las tarjetas de fidelidad y los boletos de sorteo los diseña e imprime
    Fidelidad: Configuración no crea plantillas para ellos."""
    tipo = DocumentType(document_type)
    if tipo in LOYALTY_OWNED_DOCUMENT_TYPES:
        raise DocumentInvalidValueError(
            "Las tarjetas de fidelidad y los boletos de sorteo se diseñan en Fidelidad.")
    return tipo

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


def _ensure_ticket_content(document_type, content: str) -> None:
    """Comparativa de tickets (2026-10-16): el contenido de una plantilla de
    ticket ES el diseño por bloques que imprime el POS. Texto libre (como el
    «Productos, unidad, cantidad, costo» que había en la base real) se rechaza
    con el motivo en vez de quedar como una promesa que la impresora ignora."""
    from backend.domain.document_output.ticket_layout import TICKET_DOCUMENT_TYPES, parse

    value = getattr(document_type, "value", document_type)
    if value in TICKET_DOCUMENT_TYPES:
        parse(content)


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
            document_type=_configurable(document_type), name=name, module=module,
            description=description,
        )
        _ensure_ticket_content(template.document_type, content)
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
        template = SqliteDocumentTemplateRepository(self._conn).get(current.template_id)
        if template is not None:
            _ensure_ticket_content(template.document_type, content)
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
        template = SqliteDocumentTemplateRepository(self._conn).get(version.template_id)
        if template is not None and action in (
                TemplateVersionAction.SUBMIT_FOR_APPROVAL, TemplateVersionAction.APPROVE,
                TemplateVersionAction.ACTIVATE):
            _ensure_ticket_content(template.document_type, version.content)

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
            if template is not None:
                self._deactivate_other_ticket_designs(template, version)
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

    def _deactivate_other_ticket_designs(self, template, version) -> None:
        """Un solo diseño activo por tipo de ticket: el que imprime el POS. Antes
        dos plantillas de ticket podían tener cada una su versión activa y no se
        sabía cuál mandaba."""
        from backend.domain.document_output.ticket_layout import TICKET_DOCUMENT_TYPES

        if template.document_type.value not in TICKET_DOCUMENT_TYPES:
            return
        for other in SqliteDocumentTemplateRepository(self._conn).list_by_document_type(
                template.document_type):
            if other.id == template.id:
                continue
            active = self._versions.get_active_for_template(other.id)
            if active is not None:
                active.deactivate()
                self._versions.save(active)


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
