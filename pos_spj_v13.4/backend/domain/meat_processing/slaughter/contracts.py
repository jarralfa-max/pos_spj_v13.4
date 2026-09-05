"""Slaughter contracts — future flow payload shapes (§37/§50, PROC-24).

Immutable value objects, not entities — no persistence, no use cases, no
transitions. Mirrors `backend.domain.inventory.slaughter.contracts`'s exact
style (frozen dataclasses, UUIDv7 ids, Decimal-only), scoped to the
*operational* side of the future flow: an `AnimalLotContract` is received,
inspected ante-mortem, becomes a `SlaughterOrderContract`, which produces a
carcass that Inventory's own `CarcassContract` (a different bounded context)
tracks as a lot — post-mortem inspection, classification, condemnation and
chilling all attach to that carcass reference by id, never by importing
Inventory's contract directly (bounded-context boundary, §64).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.domain.meat_processing.slaughter.enums import (
    AnimalLotStatus,
    AnteMortemDisposition,
    PostMortemDisposition,
    SlaughterOrderStatus,
)


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise MeatProcessingInvariantError("No se permite float en cantidades/pesos de faena")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class AnimalLotContract:
    lot_id: str
    branch_id: str
    warehouse_id: str
    species: str
    supplier_reference: str
    head_count: Decimal = Decimal("0")
    live_weight: Decimal = Decimal("0")
    status: AnimalLotStatus = AnimalLotStatus.RECEIVED

    def __post_init__(self) -> None:
        if not (self.lot_id and self.branch_id and self.warehouse_id):
            raise MeatProcessingInvariantError("El lote de animales requiere id, sucursal y almacén")
        if not str(self.species or "").strip():
            raise MeatProcessingInvariantError("El lote de animales requiere especie")
        object.__setattr__(self, "head_count", _dec(self.head_count))
        object.__setattr__(self, "live_weight", _dec(self.live_weight))
        if not isinstance(self.status, AnimalLotStatus):
            raise MeatProcessingInvariantError("Estado de lote de animales canónico requerido")


@dataclass(frozen=True, slots=True)
class SlaughterOrderContract:
    order_id: str
    branch_id: str
    warehouse_id: str
    animal_lot_id: str
    created_by_user_id: str
    status: SlaughterOrderStatus = SlaughterOrderStatus.DRAFT

    def __post_init__(self) -> None:
        if not (self.order_id and self.branch_id and self.warehouse_id):
            raise MeatProcessingInvariantError("La orden de sacrificio requiere id, sucursal y almacén")
        if not self.animal_lot_id:
            raise MeatProcessingInvariantError("La orden de sacrificio requiere un lote de animales")
        if not self.created_by_user_id:
            raise MeatProcessingInvariantError("La orden de sacrificio requiere quién la crea")
        if not isinstance(self.status, SlaughterOrderStatus):
            raise MeatProcessingInvariantError("Estado de orden de sacrificio canónico requerido")


@dataclass(frozen=True, slots=True)
class AnteMortemRecordContract:
    record_id: str
    animal_lot_id: str
    inspector_user_id: str
    disposition: AnteMortemDisposition
    notes: str = ""

    def __post_init__(self) -> None:
        if not (self.record_id and self.animal_lot_id and self.inspector_user_id):
            raise MeatProcessingInvariantError(
                "El registro ante mortem requiere id, lote e inspector")
        if not isinstance(self.disposition, AnteMortemDisposition):
            raise MeatProcessingInvariantError("Disposición ante mortem canónica requerida")


@dataclass(frozen=True, slots=True)
class PostMortemRecordContract:
    record_id: str
    carcass_reference_id: str
    inspector_user_id: str
    disposition: PostMortemDisposition
    notes: str = ""

    def __post_init__(self) -> None:
        if not (self.record_id and self.carcass_reference_id and self.inspector_user_id):
            raise MeatProcessingInvariantError(
                "El registro post mortem requiere id, canal e inspector")
        if not isinstance(self.disposition, PostMortemDisposition):
            raise MeatProcessingInvariantError("Disposición post mortem canónica requerida")


@dataclass(frozen=True, slots=True)
class CarcassClassificationContract:
    carcass_reference_id: str
    grade: str
    classified_by_user_id: str

    def __post_init__(self) -> None:
        if not (self.carcass_reference_id and self.classified_by_user_id):
            raise MeatProcessingInvariantError(
                "La clasificación de canal requiere canal y clasificador")
        if not str(self.grade or "").strip():
            raise MeatProcessingInvariantError("La clasificación de canal requiere grado")


@dataclass(frozen=True, slots=True)
class CondemnationRecordContract:
    record_id: str
    source_reference_id: str
    source_type: str
    reason: str
    weight: Decimal = Decimal("0")
    recorded_by_user_id: str = ""

    def __post_init__(self) -> None:
        if not (self.record_id and self.source_reference_id and self.recorded_by_user_id):
            raise MeatProcessingInvariantError(
                "El decomiso requiere id, referencia de origen y quién lo registra")
        if not str(self.source_type or "").strip():
            raise MeatProcessingInvariantError("El decomiso requiere tipo de origen")
        if not str(self.reason or "").strip():
            raise MeatProcessingInvariantError("El decomiso requiere motivo")
        object.__setattr__(self, "weight", _dec(self.weight))


@dataclass(frozen=True, slots=True)
class ChillingRecordContract:
    record_id: str
    carcass_reference_id: str
    chamber_id: str
    target_temperature_c: Decimal
    actual_temperature_c: Decimal | None = None

    def __post_init__(self) -> None:
        if not (self.record_id and self.carcass_reference_id and self.chamber_id):
            raise MeatProcessingInvariantError(
                "El registro de enfriamiento requiere id, canal y cámara")
        object.__setattr__(self, "target_temperature_c", _dec(self.target_temperature_c))
        if self.actual_temperature_c is not None:
            object.__setattr__(
                self, "actual_temperature_c", _dec(self.actual_temperature_c))
