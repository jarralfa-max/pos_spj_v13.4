"""Lead — the CRM-4 aggregate root (§16).

Status transitions:

    NEW ──assign()──► ASSIGNED ──mark_contacted()──► CONTACTED
                          │                              │
                          ├──start_nurturing()──► NURTURING ◄┘
                          │                              │
                          ├──disqualify(reason)──► UNQUALIFIED
                          ├──qualify()──► QUALIFIED ──convert()──► CONVERTED (terminal)
                          └──lose(reason)──► LOST

    UNQUALIFIED/LOST ──archive()──► ARCHIVED (terminal)

Conversion is only allowed from QUALIFIED — §18's flow assumes qualification
happened first ("la calificación... conversión" are named as separate,
sequential capabilities in §16, and §17/§18 are consecutive sections). This
entity does not implement conversion itself (that touches the Customers
bounded context) — see
backend/application/crm/use_cases/convert_lead_use_case.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.crm.enums import LeadPriority, LeadSource, LeadStatus
from backend.domain.crm.exceptions import InvalidLeadStateError
from backend.domain.crm.value_objects.lead_code import LeadCode
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _opt_decimal(value) -> Decimal | None:
    """Coerce a Decimal-like input (Decimal, whole number, numeric text, or
    None) to Decimal-or-None. Untyped on purpose (see
    backend/domain/customers/value_objects/authorization_grant.py for why a
    spelled-out union would misread as the REGLA CERO-forbidden dual-identity
    contract to a naive text scan)."""
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidLeadStateError("estimated_value debe ser Decimal, nunca float")
    return Decimal(str(value))


_ASSIGNABLE = {LeadStatus.NEW, LeadStatus.ASSIGNED, LeadStatus.CONTACTED,
               LeadStatus.NURTURING, LeadStatus.UNQUALIFIED}
_CONTACTABLE = {LeadStatus.ASSIGNED, LeadStatus.NURTURING}
_NURTURABLE = {LeadStatus.ASSIGNED, LeadStatus.CONTACTED}
_QUALIFIABLE = {LeadStatus.ASSIGNED, LeadStatus.CONTACTED, LeadStatus.NURTURING}
_DISQUALIFIABLE = {LeadStatus.NEW, LeadStatus.ASSIGNED, LeadStatus.CONTACTED,
                    LeadStatus.NURTURING}
_LOSABLE = {LeadStatus.NEW, LeadStatus.ASSIGNED, LeadStatus.CONTACTED,
            LeadStatus.NURTURING, LeadStatus.QUALIFIED}
_ARCHIVABLE = {LeadStatus.UNQUALIFIED, LeadStatus.LOST}
_TERMINAL = {LeadStatus.CONVERTED, LeadStatus.ARCHIVED}


@dataclass(slots=True)
class Lead:
    id: str
    code: LeadCode
    display_name: str
    company_name: str = ""
    contact_name: str = ""
    phone_e164: str | None = None
    email: str | None = None
    source: LeadSource = LeadSource.OTHER
    campaign_reference_id: str | None = None
    origin_branch_id: str | None = None
    assigned_user_id: str | None = None
    territory_id: str | None = None
    status: LeadStatus = LeadStatus.NEW
    score: int = 0
    priority: LeadPriority = LeadPriority.NORMAL
    estimated_value: Decimal | None = None
    expected_purchase_date: date | None = None
    last_contact_at: str | None = None
    next_action_at: str | None = None
    created_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.estimated_value = _opt_decimal(self.estimated_value)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, code: LeadCode, display_name: str, *, company_name: str = "",
        contact_name: str = "", phone_e164: str | None = None, email: str | None = None,
        source: LeadSource = LeadSource.OTHER, campaign_reference_id: str | None = None,
        origin_branch_id: str | None = None, territory_id: str | None = None,
        priority: LeadPriority = LeadPriority.NORMAL, estimated_value=None,
        expected_purchase_date: date | None = None, created_by_user_id: str | None = None,
        operation_id: str | None = None,
    ) -> "Lead":
        if not display_name or not display_name.strip():
            raise InvalidLeadStateError("display_name es obligatorio")
        return cls(
            id=new_uuid(), code=code, display_name=display_name.strip(),
            company_name=company_name.strip(), contact_name=contact_name.strip(),
            phone_e164=phone_e164, email=email, source=source,
            campaign_reference_id=campaign_reference_id, origin_branch_id=origin_branch_id,
            territory_id=territory_id, priority=priority, estimated_value=estimated_value,
            expected_purchase_date=expected_purchase_date,
            created_by_user_id=created_by_user_id, operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # lifecycle ---------------------------------------------------------------
    def assign(self, user_id: str) -> None:
        if self.status not in _ASSIGNABLE:
            raise InvalidLeadStateError(f"No se puede asignar desde {self.status.value}")
        if not user_id:
            raise InvalidLeadStateError("assign() requiere un usuario")
        self.assigned_user_id = user_id
        if self.status is LeadStatus.NEW:
            self.status = LeadStatus.ASSIGNED
        self._touch()

    def mark_contacted(self) -> None:
        if self.status not in _CONTACTABLE:
            raise InvalidLeadStateError(
                f"No se puede marcar como contactado desde {self.status.value}")
        self.status = LeadStatus.CONTACTED
        self.last_contact_at = _utcnow()
        self._touch()

    def start_nurturing(self) -> None:
        if self.status not in _NURTURABLE:
            raise InvalidLeadStateError(
                f"No se puede iniciar nutrición desde {self.status.value}")
        self.status = LeadStatus.NURTURING
        self._touch()

    def qualify(self) -> None:
        """Marks QUALIFIED. The qualification *evidence* (criteria, model,
        who decided) is a separate ``LeadQualification`` record — see
        LeadQualificationPolicy + AddLeadQualificationUseCase."""
        if self.status not in _QUALIFIABLE:
            raise InvalidLeadStateError(f"No se puede calificar desde {self.status.value}")
        self.status = LeadStatus.QUALIFIED
        self._touch()

    def disqualify(self, reason: str) -> None:
        if self.status not in _DISQUALIFIABLE:
            raise InvalidLeadStateError(f"No se puede descalificar desde {self.status.value}")
        if not reason.strip():
            raise InvalidLeadStateError("Descalificar requiere un motivo")
        self.status = LeadStatus.UNQUALIFIED
        self._touch()

    def convert(self) -> None:
        """Only flips this entity's status — the actual creation of
        Customer/Account/Contact/Opportunity is orchestrated by
        ConvertLeadUseCase, which calls this last."""
        if self.status is not LeadStatus.QUALIFIED:
            raise InvalidLeadStateError(
                f"Solo se convierte un lead calificado (está {self.status.value})")
        self.status = LeadStatus.CONVERTED
        self._touch()

    def lose(self, reason: str) -> None:
        if self.status not in _LOSABLE:
            raise InvalidLeadStateError(f"No se puede perder desde {self.status.value}")
        if not reason.strip():
            raise InvalidLeadStateError("Marcar como perdido requiere un motivo")
        self.status = LeadStatus.LOST
        self._touch()

    def archive(self) -> None:
        if self.status not in _ARCHIVABLE:
            raise InvalidLeadStateError(f"No se puede archivar desde {self.status.value}")
        self.status = LeadStatus.ARCHIVED
        self._touch()

    def record_edit(self) -> None:
        """Bump updated_at for a plain field edit (no status change)."""
        self._touch()

    def set_next_action(self, when: str | None) -> None:
        self.next_action_at = when
        self._touch()

    # capability checks -------------------------------------------------------
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def is_open(self) -> bool:
        return self.status not in _TERMINAL and self.status is not LeadStatus.LOST
