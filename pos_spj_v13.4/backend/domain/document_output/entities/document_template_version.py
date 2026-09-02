"""DocumentTemplateVersion — SET-11 (§26).

Status machine::

    DRAFT ──submit_for_approval()──► PENDING_APPROVAL ──approve()──► APPROVED ──activate()──► ACTIVE
      ▲                                    │                                                    │
      └──────────────reject(reason)────────┘                                    ┌───────────────┤
                                                                                 ▼               ▼
                                                                         deactivate()        expire()
                                                                                 │               │
                                                                                 ▼               ▼
                                                                             INACTIVE         EXPIRED
                                                                                 │               │
                                                                                 └──archive()─────┘
                                                                                       ▼
                                                                                   ARCHIVED (terminal)

Only 7 states, no REJECTED terminal — §26 doesn't list one; a rejected
version goes back to DRAFT for revision, same content but ready to be
edited and resubmitted (the caller decides whether to mutate `content`
before resubmitting — this entity doesn't erase it on reject()).
`content` is a template with placeholders, never pre-rendered output —
rendering is `DocumentRendererPort`'s job, combining this with a DTO the
owning module supplies (§27: "La plantilla no consulta tablas.").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.document_output.enums import DocumentTemplateVersionStatus, RenderFormat
from backend.domain.document_output.exceptions import (
    DocumentInvalidValueError,
    TemplateApprovalSegregationError,
    TemplateTransitionNotAllowedError,
)
from backend.shared.ids import new_uuid, validate_uuidv7

_ACTIVATABLE = {DocumentTemplateVersionStatus.APPROVED}
_DEACTIVATABLE = {DocumentTemplateVersionStatus.ACTIVE}
_EXPIRABLE = {DocumentTemplateVersionStatus.ACTIVE}
_ARCHIVABLE = {DocumentTemplateVersionStatus.INACTIVE, DocumentTemplateVersionStatus.EXPIRED}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DocumentTemplateVersion:
    id: str
    template_id: str
    version: int
    content_format: RenderFormat
    content: str
    status: DocumentTemplateVersionStatus = DocumentTemplateVersionStatus.DRAFT
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    activated_by_user_id: str | None = None
    reason: str | None = None
    previous_version_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, template_id: str, content_format: RenderFormat, content: str,
        created_by_user_id: str | None = None,
    ) -> "DocumentTemplateVersion":
        if not content.strip():
            raise DocumentInvalidValueError("content no puede estar vacío")
        return cls(
            id=new_uuid(), template_id=validate_uuidv7(template_id), version=1,
            content_format=content_format, content=content, created_by_user_id=created_by_user_id,
        )

    def create_next_version(
        self, *, content: str, created_by_user_id: str | None = None,
    ) -> "DocumentTemplateVersion":
        """A template change is never an in-place edit of an ACTIVE
        version — always a new DRAFT chained via `previous_version_id`
        (§26, same discipline as `ConfigurationValue.create_next_version()`)."""
        if not content.strip():
            raise DocumentInvalidValueError("content no puede estar vacío")
        return DocumentTemplateVersion(
            id=new_uuid(), template_id=self.template_id, version=self.version + 1,
            content_format=self.content_format, content=content, created_by_user_id=created_by_user_id,
            previous_version_id=self.id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # lifecycle ---------------------------------------------------------------
    def submit_for_approval(self) -> None:
        if self.status is not DocumentTemplateVersionStatus.DRAFT:
            raise TemplateTransitionNotAllowedError(
                f"No se puede enviar a aprobación desde {self.status.value}"
            )
        self.status = DocumentTemplateVersionStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not DocumentTemplateVersionStatus.PENDING_APPROVAL:
            raise TemplateTransitionNotAllowedError(f"No se puede aprobar desde {self.status.value}")
        if not approved_by_user_id:
            raise DocumentInvalidValueError("approve() requiere approved_by_user_id")
        if self.created_by_user_id and approved_by_user_id == self.created_by_user_id:
            raise TemplateApprovalSegregationError(
                "Quien crea una versión de plantilla no puede aprobarla; se requiere un "
                "segundo revisor (§59)"
            )
        self.status = DocumentTemplateVersionStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self._touch()

    def reject(self, reason: str) -> None:
        if self.status is not DocumentTemplateVersionStatus.PENDING_APPROVAL:
            raise TemplateTransitionNotAllowedError(f"No se puede rechazar desde {self.status.value}")
        if not reason.strip():
            raise DocumentInvalidValueError("reject() requiere un motivo")
        self.status = DocumentTemplateVersionStatus.DRAFT
        self.reason = reason.strip()
        self._touch()

    def activate(self, activated_by_user_id: str) -> None:
        if self.status not in _ACTIVATABLE:
            raise TemplateTransitionNotAllowedError(f"No se puede activar desde {self.status.value}")
        if not activated_by_user_id:
            raise DocumentInvalidValueError("activate() requiere activated_by_user_id")
        self.status = DocumentTemplateVersionStatus.ACTIVE
        self.activated_by_user_id = activated_by_user_id
        self._touch()

    def deactivate(self) -> None:
        if self.status not in _DEACTIVATABLE:
            raise TemplateTransitionNotAllowedError(f"No se puede desactivar desde {self.status.value}")
        self.status = DocumentTemplateVersionStatus.INACTIVE
        self._touch()

    def expire(self) -> None:
        if self.status not in _EXPIRABLE:
            raise TemplateTransitionNotAllowedError(f"No se puede expirar desde {self.status.value}")
        self.status = DocumentTemplateVersionStatus.EXPIRED
        self._touch()

    def archive(self) -> None:
        if self.status not in _ARCHIVABLE:
            raise TemplateTransitionNotAllowedError(f"No se puede archivar desde {self.status.value}")
        self.status = DocumentTemplateVersionStatus.ARCHIVED
        self._touch()

    def is_active(self) -> bool:
        return self.status is DocumentTemplateVersionStatus.ACTIVE
