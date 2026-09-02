"""Campaign — a marketing/retention campaign scoped to a LoyaltyProgram
(master prompt §19). ``audience_definition`` is kept as an opaque string
(no audience-segmentation engine exists in this bounded context or CRM's
own segment definitions are consumed by reference) — a future phase can
replace it with a structured value object without changing this entity's
lifecycle.

Segregation of duties (§60: "quien crea campaña no la activa solo") is
enforced directly here: ``approve()`` requires a distinct user from
``created_by_user_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import CampaignStatus, CampaignType
from backend.domain.loyalty.exceptions import (
    InvalidCampaignStateError,
    LoyaltySegregationOfDutiesError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Campaign:
    id: str
    program_id: str
    code: str
    name: str
    campaign_type: CampaignType
    created_by_user_id: str
    audience_definition: str = ""
    start_at: str | None = None
    end_at: str | None = None
    budget_limit: Decimal | None = None
    benefit_type: str = ""
    benefit_reference_id: str | None = None
    branch_scope: str | None = None
    channel_scope: str | None = None
    frequency_cap: int | None = None
    customer_cap: int | None = None
    status: CampaignStatus = CampaignStatus.DRAFT
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.program_id:
            raise InvalidCampaignStateError("program_id es obligatorio")
        if not self.code or not self.code.strip():
            raise InvalidCampaignStateError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidCampaignStateError("name es obligatorio")
        if not self.created_by_user_id:
            raise InvalidCampaignStateError("created_by_user_id es obligatorio")
        if self.budget_limit is not None:
            if isinstance(self.budget_limit, bool) or isinstance(self.budget_limit, float):
                raise InvalidCampaignStateError("budget_limit debe ser Decimal, nunca float")
            self.budget_limit = Decimal(str(self.budget_limit))
            if self.budget_limit < 0:
                raise InvalidCampaignStateError("budget_limit no puede ser negativo")

    @classmethod
    def create(
        cls, program_id: str, code: str, name: str, campaign_type: CampaignType,
        created_by_user_id: str, **kwargs,
    ) -> "Campaign":
        return cls(id=new_uuid(), program_id=program_id, code=code.strip(), name=name.strip(),
                   campaign_type=campaign_type, created_by_user_id=created_by_user_id, **kwargs)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def submit_for_approval(self) -> None:
        if self.status is not CampaignStatus.DRAFT:
            raise InvalidCampaignStateError(f"No se puede enviar desde {self.status.value}")
        self.status = CampaignStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approved_by_user_id: str) -> None:
        if self.status is not CampaignStatus.PENDING_APPROVAL:
            raise InvalidCampaignStateError(f"No se puede aprobar desde {self.status.value}")
        if not approved_by_user_id:
            raise InvalidCampaignStateError("La aprobación requiere approved_by_user_id")
        if approved_by_user_id == self.created_by_user_id:
            raise LoyaltySegregationOfDutiesError(
                "Quien crea la campaña no puede aprobarla (§60)")
        self.approved_by_user_id = approved_by_user_id
        self.status = CampaignStatus.APPROVED
        self._touch()

    def schedule(self) -> None:
        if self.status is not CampaignStatus.APPROVED:
            raise InvalidCampaignStateError(f"No se puede programar desde {self.status.value}")
        self.status = CampaignStatus.SCHEDULED
        self._touch()

    def activate(self, activated_by_user_id: str) -> None:
        if self.status not in (CampaignStatus.SCHEDULED, CampaignStatus.PAUSED):
            raise InvalidCampaignStateError(f"No se puede activar desde {self.status.value}")
        if activated_by_user_id == self.created_by_user_id:
            raise LoyaltySegregationOfDutiesError(
                "Quien crea la campaña no puede activarla solo (§60)")
        self.status = CampaignStatus.ACTIVE
        self._touch()

    def pause(self) -> None:
        if self.status is not CampaignStatus.ACTIVE:
            raise InvalidCampaignStateError(f"Solo se pausa una campaña activa")
        self.status = CampaignStatus.PAUSED
        self._touch()

    def complete(self) -> None:
        if self.status not in (CampaignStatus.ACTIVE, CampaignStatus.PAUSED):
            raise InvalidCampaignStateError(f"No se puede completar desde {self.status.value}")
        self.status = CampaignStatus.COMPLETED
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
            raise InvalidCampaignStateError(f"No se puede cancelar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidCampaignStateError("La cancelación requiere un motivo")
        self.status = CampaignStatus.CANCELLED
        self._touch()

    def is_active(self) -> bool:
        return self.status is CampaignStatus.ACTIVE
