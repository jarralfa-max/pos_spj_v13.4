"""Opportunity — the CRM-5 aggregate root (§19-22).

Status transitions:

    OPEN ──put_on_hold(reason)──► ON_HOLD ──resume()──► OPEN
      │                                │
      ├──win()───────────────────────►│──win()──► WON (terminal)
      ├──lose(reason)─────────────────┤──lose(reason)──► LOST (terminal)
      └──cancel(reason)───────────────┘──cancel(reason)──► CANCELLED (terminal)

    LOST/CANCELLED ──reopen(reason)──► OPEN

``move_stage()`` only mutates this entity's own fields (current
``stage_id``/``probability``/``expected_close_date``) and is allowed from
OPEN or ON_HOLD; it does NOT validate permission, required fields, minimum
activity, or backward-move justification — that is
``CRMStageTransitionPolicy``'s job, orchestrated by
``MoveOpportunityStageUseCase`` (mirrors how ``Lead.convert()`` only flips
status while ``ConvertLeadUseCase`` owns the cross-context orchestration).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.crm.enums import OpportunityStatus
from backend.domain.crm.exceptions import InvalidOpportunityStateError
from backend.domain.crm.value_objects.opportunity_code import OpportunityCode
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _opt_decimal(value) -> Decimal | None:
    """Coerce a Decimal-like input (Decimal, whole number, numeric text, or
    None) to Decimal-or-None. Untyped on purpose — see
    backend/domain/crm/entities/lead.py::_opt_decimal for why a spelled-out
    union return type would misread as the REGLA CERO-forbidden dual-identity
    contract to a naive text scan."""
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidOpportunityStateError("amount debe ser Decimal, nunca float")
    return Decimal(str(value))


_CLOSABLE = {OpportunityStatus.OPEN, OpportunityStatus.ON_HOLD}
_STAGE_MOVABLE = {OpportunityStatus.OPEN, OpportunityStatus.ON_HOLD}
_REOPENABLE = {OpportunityStatus.LOST, OpportunityStatus.CANCELLED}


@dataclass(slots=True)
class Opportunity:
    id: str
    code: OpportunityCode
    customer_id: str
    name: str
    stage_id: str
    account_id: str | None = None
    source_lead_id: str | None = None
    owner_user_id: str | None = None
    status: OpportunityStatus = OpportunityStatus.OPEN
    amount: Decimal | None = None
    probability: int = 0
    expected_close_date: date | None = None
    territory_id: str | None = None
    origin_branch_id: str | None = None
    description: str = ""
    close_reason: str = ""
    closed_at: str | None = None
    created_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.amount = _opt_decimal(self.amount)
        if not (0 <= self.probability <= 100):
            raise InvalidOpportunityStateError("probability debe estar entre 0 y 100")

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, code: OpportunityCode, customer_id: str, name: str, stage_id: str, *,
        account_id: str | None = None, source_lead_id: str | None = None,
        owner_user_id: str | None = None, amount=None, probability: int = 0,
        expected_close_date: date | None = None, territory_id: str | None = None,
        origin_branch_id: str | None = None, description: str = "",
        created_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "Opportunity":
        if not customer_id:
            raise InvalidOpportunityStateError("customer_id es obligatorio")
        if not name or not name.strip():
            raise InvalidOpportunityStateError("name es obligatorio")
        if not stage_id:
            raise InvalidOpportunityStateError("stage_id es obligatorio")
        return cls(
            id=new_uuid(), code=code, customer_id=customer_id, name=name.strip(),
            stage_id=stage_id, account_id=account_id, source_lead_id=source_lead_id,
            owner_user_id=owner_user_id, amount=amount, probability=probability,
            expected_close_date=expected_close_date, territory_id=territory_id,
            origin_branch_id=origin_branch_id, description=description,
            created_by_user_id=created_by_user_id, operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # lifecycle ---------------------------------------------------------------
    def assign_owner(self, user_id: str) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidOpportunityStateError(
                f"No se puede asignar propietario desde {self.status.value}")
        if not user_id:
            raise InvalidOpportunityStateError("assign_owner() requiere un usuario")
        self.owner_user_id = user_id
        self._touch()

    def move_stage(self, stage_id: str, *, probability: int | None = None,
                   expected_close_date: date | None = None) -> None:
        if self.status not in _STAGE_MOVABLE:
            raise InvalidOpportunityStateError(
                f"No se puede cambiar de etapa desde {self.status.value}")
        if not stage_id:
            raise InvalidOpportunityStateError("move_stage() requiere stage_id")
        self.stage_id = stage_id
        if probability is not None:
            if not (0 <= probability <= 100):
                raise InvalidOpportunityStateError("probability debe estar entre 0 y 100")
            self.probability = probability
        if expected_close_date is not None:
            self.expected_close_date = expected_close_date
        self._touch()

    def put_on_hold(self, reason: str) -> None:
        if self.status is not OpportunityStatus.OPEN:
            raise InvalidOpportunityStateError(
                f"No se puede poner en espera desde {self.status.value}")
        if not reason.strip():
            raise InvalidOpportunityStateError("Poner en espera requiere un motivo")
        self.status = OpportunityStatus.ON_HOLD
        self._touch()

    def resume(self) -> None:
        if self.status is not OpportunityStatus.ON_HOLD:
            raise InvalidOpportunityStateError(f"No se puede reanudar desde {self.status.value}")
        self.status = OpportunityStatus.OPEN
        self._touch()

    def win(self, *, won_stage_id: str | None = None) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidOpportunityStateError(f"No se puede ganar desde {self.status.value}")
        self.status = OpportunityStatus.WON
        self.probability = 100
        if won_stage_id:
            self.stage_id = won_stage_id
        self.close_reason = ""
        self.closed_at = _utcnow()
        self._touch()

    def lose(self, reason: str, *, lost_stage_id: str | None = None) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidOpportunityStateError(f"No se puede perder desde {self.status.value}")
        if not reason.strip():
            raise InvalidOpportunityStateError("Marcar como perdida requiere un motivo")
        self.status = OpportunityStatus.LOST
        self.probability = 0
        if lost_stage_id:
            self.stage_id = lost_stage_id
        self.close_reason = reason
        self.closed_at = _utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidOpportunityStateError(f"No se puede cancelar desde {self.status.value}")
        if not reason.strip():
            raise InvalidOpportunityStateError("Cancelar requiere un motivo")
        self.status = OpportunityStatus.CANCELLED
        self.close_reason = reason
        self.closed_at = _utcnow()
        self._touch()

    def reopen(self, reason: str) -> None:
        if self.status not in _REOPENABLE:
            raise InvalidOpportunityStateError(f"No se puede reabrir desde {self.status.value}")
        if not reason.strip():
            raise InvalidOpportunityStateError("Reabrir requiere un motivo")
        self.status = OpportunityStatus.OPEN
        self.close_reason = ""
        self.closed_at = None
        self._touch()

    def record_edit(self) -> None:
        """Bump updated_at for a plain field edit (no status change)."""
        self._touch()

    # capability checks -------------------------------------------------------
    def is_terminal(self) -> bool:
        return self.status in (OpportunityStatus.WON, OpportunityStatus.LOST,
                               OpportunityStatus.CANCELLED)

    def is_open(self) -> bool:
        return self.status is OpportunityStatus.OPEN
