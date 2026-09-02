"""ContentCampaign — SET-18 "Campaigns"/"Approval".

Status machine (mirrors
`backend.domain.document_output.entities.document_template_version.
DocumentTemplateVersion`'s exact shape, SET-11)::

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

Only ACTIVE campaigns may ever be placed on an `AdvertisingSlot` — see
`policies/campaign_placement_policy.py::assign_placement()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.enums import ContentCampaignStatus
from backend.domain.customer_display.exceptions import (
    ContentCampaignApprovalSegregationError,
    ContentCampaignTransitionNotAllowedError,
    CustomerDisplayInvalidValueError,
)
from backend.shared.ids import new_uuid, validate_uuidv7

_ACTIVATABLE = {ContentCampaignStatus.APPROVED}
_DEACTIVATABLE = {ContentCampaignStatus.ACTIVE}
_EXPIRABLE = {ContentCampaignStatus.ACTIVE}
_ARCHIVABLE = {ContentCampaignStatus.INACTIVE, ContentCampaignStatus.EXPIRED}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ContentCampaign:
    id: str
    name: str
    content_id: str
    status: ContentCampaignStatus = ContentCampaignStatus.DRAFT
    starts_at: str | None = None
    ends_at: str | None = None
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    activated_by_user_id: str | None = None
    reason: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, name: str, content_id: str, starts_at: str | None = None, ends_at: str | None = None,
        created_by_user_id: str | None = None,
    ) -> "ContentCampaign":
        if not name.strip():
            raise CustomerDisplayInvalidValueError("name es obligatorio")
        if starts_at and ends_at and ends_at < starts_at:
            raise CustomerDisplayInvalidValueError("ends_at no puede ser anterior a starts_at")
        return cls(
            id=new_uuid(), name=name.strip(), content_id=validate_uuidv7(content_id), starts_at=starts_at,
            ends_at=ends_at, created_by_user_id=created_by_user_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_schedule(self, *, starts_at: str | None, ends_at: str | None) -> None:
        if starts_at and ends_at and ends_at < starts_at:
            raise CustomerDisplayInvalidValueError("ends_at no puede ser anterior a starts_at")
        self.starts_at = starts_at
        self.ends_at = ends_at
        self._touch()

    # lifecycle -----------------------------------------------------------------
    def submit_for_approval(self) -> None:
        if self.status is not ContentCampaignStatus.DRAFT:
            raise ContentCampaignTransitionNotAllowedError(
                f"No se puede enviar a aprobación desde {self.status.value}"
            )
        self.status = ContentCampaignStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not ContentCampaignStatus.PENDING_APPROVAL:
            raise ContentCampaignTransitionNotAllowedError(f"No se puede aprobar desde {self.status.value}")
        if not approved_by_user_id:
            raise CustomerDisplayInvalidValueError("approve() requiere approved_by_user_id")
        if self.created_by_user_id and approved_by_user_id == self.created_by_user_id:
            raise ContentCampaignApprovalSegregationError(
                "Quien crea una campaña no puede aprobarla; se requiere un segundo revisor (§59)"
            )
        self.status = ContentCampaignStatus.APPROVED
        self.approved_by_user_id = approved_by_user_id
        self._touch()

    def reject(self, reason: str) -> None:
        if self.status is not ContentCampaignStatus.PENDING_APPROVAL:
            raise ContentCampaignTransitionNotAllowedError(f"No se puede rechazar desde {self.status.value}")
        if not reason.strip():
            raise CustomerDisplayInvalidValueError("reject() requiere un motivo")
        self.status = ContentCampaignStatus.DRAFT
        self.reason = reason.strip()
        self._touch()

    def activate(self, activated_by_user_id: str) -> None:
        if self.status not in _ACTIVATABLE:
            raise ContentCampaignTransitionNotAllowedError(f"No se puede activar desde {self.status.value}")
        if not activated_by_user_id:
            raise CustomerDisplayInvalidValueError("activate() requiere activated_by_user_id")
        self.status = ContentCampaignStatus.ACTIVE
        self.activated_by_user_id = activated_by_user_id
        self._touch()

    def deactivate(self) -> None:
        if self.status not in _DEACTIVATABLE:
            raise ContentCampaignTransitionNotAllowedError(f"No se puede desactivar desde {self.status.value}")
        self.status = ContentCampaignStatus.INACTIVE
        self._touch()

    def expire(self) -> None:
        if self.status not in _EXPIRABLE:
            raise ContentCampaignTransitionNotAllowedError(f"No se puede expirar desde {self.status.value}")
        self.status = ContentCampaignStatus.EXPIRED
        self._touch()

    def archive(self) -> None:
        if self.status not in _ARCHIVABLE:
            raise ContentCampaignTransitionNotAllowedError(f"No se puede archivar desde {self.status.value}")
        self.status = ContentCampaignStatus.ARCHIVED
        self._touch()

    def is_active(self) -> bool:
        return self.status is ContentCampaignStatus.ACTIVE
