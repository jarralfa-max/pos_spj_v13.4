"""InstrumentBatch — un lote físico de cupones o vales (auditoría de Fidelidad
968e0bc, ampliación).

El lote es el documento que se diseña, aprueba, imprime y activa; cada pieza es
una instancia propia (`coupon_instances` / `voucher_instances`) con su folio y un
token público ÚNICO. El código impreso identifica UNA pieza, nunca el lote.

Ciclo: DRAFT → PENDING_APPROVAL → APPROVED → PRINTED → ACTIVATED, y CANCELLED
desde cualquier estado anterior a ACTIVATED. Quien crea no aprueba.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from backend.domain.commercial_instruments.exceptions import CommercialInstrumentDomainError
from backend.domain.commercial_instruments.value_objects.redemption_rules import (
    FundingSource,
    LeftoverPolicy,
    PercentBase,
    RedemptionMode,
    RedemptionRules,
)
from backend.shared.ids import new_uuid

#: Tope de piezas por lote: un lote más grande se parte en varios (imprimir
#: miles de códigos de una vez es más fácil de perder que de controlar).
MAX_BATCH_QUANTITY = 5000


class InstrumentKind(str, Enum):
    COUPON = "COUPON"
    VOUCHER = "VOUCHER"

    @property
    def prefix(self) -> str:
        return "CUP" if self is InstrumentKind.COUPON else "VAL"


class BatchStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PRINTED = "PRINTED"
    ACTIVATED = "ACTIVATED"
    CANCELLED = "CANCELLED"


class InstrumentBatchError(CommercialInstrumentDomainError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class InstrumentBatch:
    id: str
    kind: InstrumentKind
    definition_id: str
    name: str
    quantity: int
    unit_value: Decimal
    funding_source: FundingSource
    created_by_user_id: str
    status: BatchStatus = BatchStatus.DRAFT
    valid_from: str | None = None
    valid_to: str | None = None
    branch_ids: tuple[str, ...] = ()
    redemption_mode: RedemptionMode = RedemptionMode.MULTI_EVENT
    max_redemptions: int | None = None
    max_percent_per_sale: Decimal | None = None
    percent_base: PercentBase = PercentBase.GROSS
    leftover_policy: LeftoverPolicy = LeftoverPolicy.REQUIRE_FULL_USE
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    printed_count: int = 0
    activated_at: str | None = None
    cancelled_reason: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.definition_id:
            raise InstrumentBatchError("El lote necesita una definición de cupón o vale")
        if not str(self.name or "").strip():
            raise InstrumentBatchError("El lote necesita un nombre")
        if not 1 <= int(self.quantity) <= MAX_BATCH_QUANTITY:
            raise InstrumentBatchError(f"La cantidad va de 1 a {MAX_BATCH_QUANTITY} piezas")
        if not isinstance(self.unit_value, Decimal) or self.unit_value < 0:
            raise InstrumentBatchError("El valor unitario debe ser un Decimal no negativo")
        if self.kind is InstrumentKind.VOUCHER and self.unit_value <= 0:
            raise InstrumentBatchError("Un vale necesita un importe mayor a cero")
        if self.kind is InstrumentKind.COUPON:
            # Un cupón es un descuento de un solo uso, siempre (decisión del informe).
            self.redemption_mode = RedemptionMode.ONE_EVENT
            self.max_redemptions = 1
            self.max_percent_per_sale = None
        if self.funding_source is FundingSource.PREPAID:
            # Un prepago se activa al COBRARSE cada pieza, en el POS; no por lote.
            raise InstrumentBatchError(
                "Los vales prepagados se venden en caja, uno por uno; no se emiten por lote")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise InstrumentBatchError("La vigencia termina antes de empezar")
        self.rules()  # valida la combinación de reglas

    # ── construcción ─────────────────────────────────────────────────────
    @classmethod
    def draft(cls, **datos) -> "InstrumentBatch":
        return cls(id=new_uuid(), **datos)

    def rules(self) -> RedemptionRules:
        return RedemptionRules(
            mode=self.redemption_mode, max_redemptions=self.max_redemptions,
            max_percent_per_sale=self.max_percent_per_sale, percent_base=self.percent_base,
            leftover_policy=self.leftover_policy, funding_source=self.funding_source)

    @property
    def branch_ids_json(self) -> str:
        return json.dumps(list(self.branch_ids))

    # ── ciclo de vida ────────────────────────────────────────────────────
    def _require(self, *estados: BatchStatus) -> None:
        if self.status not in estados:
            raise InstrumentBatchError(
                f"El lote está en {self.status.value}; esta acción no aplica")

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def submit(self) -> None:
        self._require(BatchStatus.DRAFT)
        self.status = BatchStatus.PENDING_APPROVAL
        self._touch()

    def approve(self, approver_user_id: str) -> None:
        self._require(BatchStatus.PENDING_APPROVAL)
        if not approver_user_id:
            raise InstrumentBatchError("La aprobación requiere un usuario")
        if approver_user_id == self.created_by_user_id:
            raise InstrumentBatchError("Quien crea el lote no puede aprobarlo")
        self.status = BatchStatus.APPROVED
        self.approved_by_user_id = approver_user_id
        self.approved_at = _utcnow()
        self._touch()

    def mark_printed(self) -> None:
        self._require(BatchStatus.APPROVED, BatchStatus.PRINTED, BatchStatus.ACTIVATED)
        if self.status is BatchStatus.APPROVED:
            self.status = BatchStatus.PRINTED
        self.printed_count += 1
        self._touch()

    def activate(self) -> None:
        self._require(BatchStatus.PRINTED)
        self.status = BatchStatus.ACTIVATED
        self.activated_at = _utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        self._require(BatchStatus.DRAFT, BatchStatus.PENDING_APPROVAL, BatchStatus.APPROVED,
                      BatchStatus.PRINTED)
        if not str(reason or "").strip():
            raise InstrumentBatchError("Cancelar un lote requiere motivo")
        self.status = BatchStatus.CANCELLED
        self.cancelled_reason = reason.strip()
        self._touch()

    # ── uso ──────────────────────────────────────────────────────────────
    def valid_at(self, instante: str) -> bool:
        """La vigencia es por DÍA (`AAAA-MM-DD`, ambos extremos incluidos)."""
        dia = str(instante or "")[:10]
        return ((not self.valid_from or dia >= self.valid_from[:10])
                and (not self.valid_to or dia <= self.valid_to[:10]))

    def allows_branch(self, branch_id: str) -> bool:
        return not self.branch_ids or str(branch_id or "") in self.branch_ids


__all__ = ["BatchStatus", "InstrumentBatch", "InstrumentBatchError", "InstrumentKind",
           "MAX_BATCH_QUANTITY"]
