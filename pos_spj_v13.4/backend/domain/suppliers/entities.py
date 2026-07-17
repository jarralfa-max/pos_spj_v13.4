"""Entities for the suppliers bounded context.

``Supplier`` is the aggregate root: it owns status transitions and process
blocks and protects the lifecycle invariants. Child entities (contacts,
addresses, bank accounts, terms, products, documents, evaluations, risk, branch
authorizations) are separate structures, never merged into the supplier row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.suppliers.enums import (
    AddressType,
    BankAccountStatus,
    BlockType,
    CommercialCategory,
    ContactType,
    DocumentStatus,
    DocumentType,
    EvaluationDimension,
    RiskLevel,
    SupplierClassification,
    SupplierStatus,
)
from backend.domain.suppliers.exceptions import (
    BankAccountNotVerifiedError,
    InvalidEvaluationError,
    InvalidSupplierStateError,
    RejectedSupplierReactivationError,
    SupplierDeletionForbiddenError,
)
from backend.domain.suppliers.value_objects import (
    Money,
    PaymentTerms,
    RatingBands,
    SupplierCode,
    SupplierRating,
    TaxIdentifier,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── blocks ───────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class SupplierBlock:
    id: str
    supplier_id: str
    block_type: BlockType
    reason: str
    created_by_user_id: str
    operation_id: str
    effective_at: str = field(default_factory=_utcnow)
    expires_at: str | None = None
    approved_by_user_id: str | None = None
    active: bool = True

    @classmethod
    def create(cls, supplier_id: str, block_type: BlockType, reason: str,
               created_by_user_id: str, operation_id: str, *,
               expires_at: str | None = None,
               approved_by_user_id: str | None = None) -> "SupplierBlock":
        if not reason or not reason.strip():
            raise InvalidSupplierStateError("El bloqueo requiere un motivo")
        return cls(id=new_uuid(), supplier_id=supplier_id, block_type=block_type,
                   reason=reason.strip(), created_by_user_id=created_by_user_id,
                   operation_id=operation_id, expires_at=expires_at,
                   approved_by_user_id=approved_by_user_id)


# ── aggregate root ────────────────────────────────────────────────────────────
_TERMINAL = {SupplierStatus.INACTIVE, SupplierStatus.REJECTED}


@dataclass(slots=True)
class Supplier:
    id: str
    code: SupplierCode
    legal_name: str
    trade_name: str
    tax_identifier: TaxIdentifier | None
    status: SupplierStatus = SupplierStatus.DRAFT
    tax_regime: str | None = None
    country_code: str = "MX"
    preferred_currency: str = "MXN"
    language: str = "es-MX"
    website: str | None = None
    notes: str = ""
    classifications: set[SupplierClassification] = field(default_factory=set)
    categories: set[CommercialCategory] = field(default_factory=set)
    blocks: list[SupplierBlock] = field(default_factory=list)
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    has_history: bool = False
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(cls, code: SupplierCode, legal_name: str, *, trade_name: str = "",
               tax_identifier: TaxIdentifier | None = None,
               created_by_user_id: str | None = None,
               preferred_currency: str = "MXN", country_code: str = "MX",
               classifications: set[SupplierClassification] | None = None,
               categories: set[CommercialCategory] | None = None) -> "Supplier":
        if not legal_name or not legal_name.strip():
            raise InvalidSupplierStateError("La razón social es obligatoria")
        return cls(
            id=new_uuid(), code=code, legal_name=legal_name.strip(),
            trade_name=(trade_name or legal_name).strip(), tax_identifier=tax_identifier,
            created_by_user_id=created_by_user_id, preferred_currency=preferred_currency,
            country_code=country_code, classifications=set(classifications or set()),
            categories=set(categories or set()))

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # lifecycle ---------------------------------------------------------------
    def submit_for_approval(self) -> None:
        if self.status is not SupplierStatus.DRAFT:
            raise InvalidSupplierStateError(
                f"Solo un borrador se envía a aprobación (está {self.status.value})")
        if self.tax_identifier is None:
            raise InvalidSupplierStateError("Falta el identificador fiscal para aprobar")
        self.status = SupplierStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approver_user_id: str) -> None:
        if self.status is not SupplierStatus.PENDING_APPROVAL:
            raise InvalidSupplierStateError(
                f"Solo se aprueba una solicitud pendiente (está {self.status.value})")
        self.status = SupplierStatus.ACTIVE
        self.approved_by_user_id = approver_user_id
        self._touch()

    def reject(self, approver_user_id: str, reason: str = "") -> None:
        if self.status is not SupplierStatus.PENDING_APPROVAL:
            raise InvalidSupplierStateError("Solo se rechaza una solicitud pendiente")
        self.status = SupplierStatus.REJECTED
        self.approved_by_user_id = approver_user_id
        if reason:
            self.notes = (self.notes + f"\n[Rechazo] {reason}").strip()
        self._touch()

    def activate(self) -> None:
        """Re-activate a suspended supplier (not a rejected one)."""
        if self.status is SupplierStatus.REJECTED:
            raise RejectedSupplierReactivationError(
                "Un proveedor rechazado requiere un nuevo workflow de alta")
        if self.status not in (SupplierStatus.SUSPENDED, SupplierStatus.BLOCKED):
            raise InvalidSupplierStateError(
                f"No se puede activar desde {self.status.value}")
        # only clear a general block on activation; process blocks are explicit
        self.blocks = [b for b in self.blocks
                       if not (b.block_type is BlockType.GENERAL_BLOCK and b.active)]
        self.status = SupplierStatus.ACTIVE
        self._touch()

    def suspend(self, reason: str) -> None:
        if self.status is not SupplierStatus.ACTIVE:
            raise InvalidSupplierStateError("Solo se suspende un proveedor activo")
        if not reason.strip():
            raise InvalidSupplierStateError("La suspensión requiere un motivo")
        self.status = SupplierStatus.SUSPENDED
        self._touch()

    def deactivate(self) -> None:
        """Operational shutdown that preserves history (never a physical delete)."""
        if self.status is SupplierStatus.DRAFT:
            raise InvalidSupplierStateError("Un borrador no se da de baja; se descarta")
        self.status = SupplierStatus.INACTIVE
        self._touch()

    # blocks ------------------------------------------------------------------
    def apply_block(self, block: SupplierBlock) -> None:
        self.blocks = [b for b in self.blocks if b.block_type is not block.block_type]
        self.blocks.append(block)
        if block.block_type is BlockType.GENERAL_BLOCK:
            self.status = SupplierStatus.BLOCKED
        self._touch()

    def remove_block(self, block_type: BlockType) -> None:
        remaining = [b for b in self.blocks if b.block_type is not block_type]
        self.blocks = remaining
        if block_type is BlockType.GENERAL_BLOCK and self.status is SupplierStatus.BLOCKED:
            self.status = SupplierStatus.ACTIVE
        self._touch()

    def has_block(self, block_type: BlockType) -> bool:
        return any(b.block_type is block_type and b.active for b in self.blocks)

    # capability checks -------------------------------------------------------
    def is_operational(self) -> bool:
        return self.status is SupplierStatus.ACTIVE

    def can_purchase(self) -> bool:
        return self.is_operational() and not self.has_block(BlockType.PURCHASING_BLOCK) \
            and not self.has_block(BlockType.GENERAL_BLOCK)

    def can_receive(self) -> bool:
        return self.status in (SupplierStatus.ACTIVE, SupplierStatus.SUSPENDED) \
            and not self.has_block(BlockType.RECEIVING_BLOCK) \
            and not self.has_block(BlockType.GENERAL_BLOCK)

    def can_pay(self) -> bool:
        return self.status in (SupplierStatus.ACTIVE, SupplierStatus.SUSPENDED,
                               SupplierStatus.BLOCKED) \
            and not self.has_block(BlockType.PAYMENT_BLOCK) \
            and not self.has_block(BlockType.GENERAL_BLOCK)

    # invariants --------------------------------------------------------------
    def assert_deletable(self) -> None:
        if self.has_history:
            raise SupplierDeletionForbiddenError(
                "No se elimina un proveedor con historial; usa baja (INACTIVE)")


# ── child entities ────────────────────────────────────────────────────────────
@dataclass(slots=True)
class SupplierContact:
    id: str
    supplier_id: str
    name: str
    contact_type: ContactType
    role: str = ""
    phone_e164: str | None = None
    email: str | None = None
    is_primary: bool = False
    receives_purchase_orders: bool = False
    receives_payment_receipts: bool = False
    receives_notifications: bool = False
    active: bool = True

    @classmethod
    def create(cls, supplier_id: str, name: str, contact_type: ContactType,
               **kwargs) -> "SupplierContact":
        if not name.strip():
            raise InvalidSupplierStateError("El contacto requiere nombre")
        return cls(id=new_uuid(), supplier_id=supplier_id, name=name.strip(),
                   contact_type=contact_type, **kwargs)


@dataclass(slots=True)
class SupplierAddress:
    id: str
    supplier_id: str
    address_type: AddressType
    line: str
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country_code: str = "MX"
    latitude: float | None = None
    longitude: float | None = None
    geocoding_source: str | None = None
    validation_state: str = "MANUAL"

    @classmethod
    def create(cls, supplier_id: str, address_type: AddressType, line: str,
               **kwargs) -> "SupplierAddress":
        return cls(id=new_uuid(), supplier_id=supplier_id, address_type=address_type,
                   line=line.strip(), **kwargs)


@dataclass(slots=True)
class SupplierBankAccount:
    id: str
    supplier_id: str
    bank_name: str
    account_holder: str
    currency_code: str = "MXN"
    account_type: str = "CHECKING"
    account_number: str = ""
    clabe: str = ""
    swift_bic: str = ""
    country_code: str = "MX"
    status: BankAccountStatus = BankAccountStatus.UNVERIFIED
    document_reference: str | None = None
    verified_by_user_id: str | None = None
    verified_at: str | None = None

    @classmethod
    def create(cls, supplier_id: str, bank_name: str, account_holder: str,
               **kwargs) -> "SupplierBankAccount":
        return cls(id=new_uuid(), supplier_id=supplier_id, bank_name=bank_name.strip(),
                   account_holder=account_holder.strip(), **kwargs)

    def submit_for_verification(self) -> None:
        if self.status in (BankAccountStatus.VERIFIED, BankAccountStatus.BLOCKED):
            raise InvalidSupplierStateError(
                f"La cuenta está {self.status.value}; no requiere verificación")
        self.status = BankAccountStatus.PENDING_VERIFICATION

    def verify(self, verified_by_user_id: str) -> None:
        if self.status not in (BankAccountStatus.PENDING_VERIFICATION,
                               BankAccountStatus.UNVERIFIED):
            raise InvalidSupplierStateError(
                f"No se puede verificar una cuenta {self.status.value}")
        self.status = BankAccountStatus.VERIFIED
        self.verified_by_user_id = verified_by_user_id
        self.verified_at = _utcnow()

    def reject(self, reason: str = "") -> None:
        self.status = BankAccountStatus.REJECTED

    def invalidate_on_change(self) -> None:
        """Any bank-data change resets verification (policy: no instant pay)."""
        self.status = BankAccountStatus.PENDING_VERIFICATION
        self.verified_by_user_id = None
        self.verified_at = None

    def assert_usable_for_payment(self) -> None:
        if self.status is not BankAccountStatus.VERIFIED:
            raise BankAccountNotVerifiedError(
                "La cuenta bancaria no está verificada; no puede usarse para pagar")

    def masked_clabe(self) -> str:
        digits = "".join(ch for ch in self.clabe if ch.isdigit())
        return ("•" * max(0, len(digits) - 4)) + digits[-4:] if digits else ""


@dataclass(slots=True)
class SupplierCommercialTerms:
    id: str
    supplier_id: str
    payment_terms: PaymentTerms
    price_list: str | None = None
    lead_time_days: int = 0
    delivery_days: str = ""            # e.g. "1,2,3,4,5" weekdays
    receiving_window_start: str | None = None  # HH:mm
    receiving_window_end: str | None = None
    accepts_returns: bool = True
    return_window_days: int = 0
    currency_code: str = "MXN"

    @classmethod
    def create(cls, supplier_id: str, payment_terms: PaymentTerms,
               **kwargs) -> "SupplierCommercialTerms":
        return cls(id=new_uuid(), supplier_id=supplier_id, payment_terms=payment_terms,
                   **kwargs)


@dataclass(slots=True)
class SupplierProduct:
    id: str
    supplier_id: str
    product_id: str
    supplier_sku: str = ""
    supplier_description: str = ""
    purchase_unit: str = ""
    conversion_factor: str = "1"
    minimum_order_quantity: str = "0"
    package_size: str = "1"
    lead_time_days: int = 0
    last_cost: Money | None = None
    current_cost: Money | None = None
    currency_code: str = "MXN"
    preferred: bool = False
    active: bool = True
    valid_from: date | None = None
    valid_to: date | None = None

    @classmethod
    def create(cls, supplier_id: str, product_id: str, **kwargs) -> "SupplierProduct":
        return cls(id=new_uuid(), supplier_id=supplier_id, product_id=product_id, **kwargs)


@dataclass(slots=True)
class SupplierDocument:
    id: str
    supplier_id: str
    document_type: DocumentType
    file_reference: str
    status: DocumentStatus = DocumentStatus.PENDING_REVIEW
    issued_at: date | None = None
    expires_at: date | None = None
    verified_by_user_id: str | None = None
    verified_at: str | None = None
    notes: str = ""

    @classmethod
    def create(cls, supplier_id: str, document_type: DocumentType,
               file_reference: str, **kwargs) -> "SupplierDocument":
        return cls(id=new_uuid(), supplier_id=supplier_id, document_type=document_type,
                   file_reference=file_reference, **kwargs)

    def compute_status(self, today: date, *, expiring_days: int = 30) -> DocumentStatus:
        if self.status in (DocumentStatus.PENDING_REVIEW, DocumentStatus.REJECTED):
            return self.status
        if self.expires_at is None:
            return DocumentStatus.VALID
        if self.expires_at < today:
            return DocumentStatus.EXPIRED
        if (self.expires_at - today).days <= expiring_days:
            return DocumentStatus.EXPIRING
        return DocumentStatus.VALID


@dataclass(slots=True)
class SupplierEvaluationItem:
    dimension: EvaluationDimension
    score: int          # 0..100
    weight: Decimal | None = None


@dataclass(slots=True)
class SupplierEvaluation:
    id: str
    supplier_id: str
    period: str                       # e.g. "2026-07"
    items: list[SupplierEvaluationItem]
    evaluated_by_user_id: str
    comments: str = ""
    evidence_reference: str | None = None
    score: int = 0
    rating: SupplierRating | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, supplier_id: str, period: str,
               items: list[SupplierEvaluationItem], evaluated_by_user_id: str,
               *, bands: RatingBands | None = None, **kwargs) -> "SupplierEvaluation":
        if not items:
            raise InvalidEvaluationError("La evaluación requiere al menos una dimensión")
        score = cls._weighted_score(items)
        return cls(id=new_uuid(), supplier_id=supplier_id, period=period, items=items,
                   evaluated_by_user_id=evaluated_by_user_id, score=score,
                   rating=SupplierRating.from_score(score, bands), **kwargs)

    @staticmethod
    def _weighted_score(items: list[SupplierEvaluationItem]) -> int:
        weights = [Decimal(str(i.weight)) if i.weight is not None else Decimal("1")
                   for i in items]
        total_weight = sum(weights) or Decimal("1")
        weighted = sum(Decimal(i.score) * w for i, w in zip(items, weights))
        return int((weighted / total_weight).to_integral_value())


@dataclass(slots=True)
class SupplierRiskFactor:
    code: str
    description: str
    severity: int = 1   # contribution weight


@dataclass(slots=True)
class SupplierRisk:
    supplier_id: str
    level: RiskLevel
    factors: list[SupplierRiskFactor] = field(default_factory=list)
    computed_at: str = field(default_factory=_utcnow)

    def explanation(self) -> list[str]:
        """Risk must explain its causes (never just a color)."""
        return [f.description for f in self.factors]


@dataclass(slots=True)
class SupplierBranchAuthorization:
    id: str
    supplier_id: str
    branch_id: str
    can_purchase: bool = True
    can_receive: bool = True
    can_pay: bool = True
    preferred: bool = False
    active: bool = True

    @classmethod
    def create(cls, supplier_id: str, branch_id: str, **kwargs) -> "SupplierBranchAuthorization":
        return cls(id=new_uuid(), supplier_id=supplier_id, branch_id=branch_id, **kwargs)
