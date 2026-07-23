"""Product — the master-data aggregate root (§10).

Product answers *what an article is*, never *how much exists* (Inventory) nor
*what it sells for* (Pricing). It carries identity (UUIDv7), classification,
control flags, functional roles and lifecycle — but no ``existencia`` and no final
price. Those columns are guardrail-forbidden here and live in their own bounded
contexts.

Lifecycle transitions are validated against ``product_lifecycle_policy`` so the
legal-state rule lives in exactly one place. A product with history is never
deleted — it is discontinued and archived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.products.enums import (
    MEAT_PRODUCT_TYPES,
    LifecycleStatus,
    ProductRole,
    ProductType,
)
from backend.domain.products.exceptions import (
    InvalidProductStateError,
    ProductIncompleteError,
    ProductsDomainError,
    SpeciesRequiredError,
)
from backend.domain.products.policies.product_lifecycle_policy import can_transition
from backend.domain.products.value_objects.product_code import ProductCode
from backend.domain.products.value_objects.product_name import ProductName
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Product:
    code: ProductCode
    name: ProductName
    product_type: ProductType
    base_unit_id: str
    id: str = field(default_factory=new_uuid)
    lifecycle_status: LifecycleStatus = LifecycleStatus.DRAFT

    short_name: str | None = None
    description: str | None = None
    category_id: str | None = None
    brand_id: str | None = None
    species_id: str | None = None          # required for meat types (PROD-3)
    tax_profile_id: str | None = None
    country_of_origin: str | None = None

    # ── control flags (§10) ──────────────────────────────────────────────
    sellable: bool = False
    purchasable: bool = False
    inventory_managed: bool = False
    producible: bool = False
    internal_only: bool = False
    recipe_allowed: bool = False
    bundle_allowed: bool = False
    lot_controlled: bool = False
    serial_controlled: bool = False
    expiration_controlled: bool = False
    catch_weight_enabled: bool = False
    quality_controlled: bool = False
    traceability_required: bool = False

    created_by: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    activated_at: str | None = None
    discontinued_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProductCode):
            self.code = ProductCode(str(self.code))
        if not isinstance(self.name, ProductName):
            self.name = ProductName(str(self.name))
        if not isinstance(self.product_type, ProductType):
            self.product_type = ProductType(str(self.product_type))
        if not self.base_unit_id:
            raise ProductsDomainError("El producto requiere una unidad base (§7)")
        if self.internal_only and self.sellable:
            raise ProductsDomainError(
                "Un producto interno (INTERNAL_ONLY) no puede ser vendible (§13)")

    # ── clasificación ────────────────────────────────────────────────────
    @property
    def is_meat(self) -> bool:
        return self.product_type in MEAT_PRODUCT_TYPES

    @property
    def roles(self) -> frozenset[ProductRole]:
        """Roles funcionales derivados de las banderas de control (§5)."""
        r: set[ProductRole] = set()
        if self.sellable:
            r.add(ProductRole.SELLABLE)
        if self.purchasable:
            r.add(ProductRole.PURCHASABLE)
        if self.inventory_managed:
            r.add(ProductRole.INVENTORY_MANAGED)
        if self.producible:
            r.add(ProductRole.PRODUCIBLE)
        if self.internal_only:
            r.add(ProductRole.INTERNAL_ONLY)
        if self.quality_controlled:
            r.add(ProductRole.QUALITY_CONTROLLED)
        if self.traceability_required:
            r.add(ProductRole.TRACEABLE)
        return frozenset(r)

    # ── invariantes de completitud (§7) ──────────────────────────────────
    def missing_activation_data(self) -> list[str]:
        """Datos maestros faltantes que impiden activar (§7, §35)."""
        missing: list[str] = []
        if not self.base_unit_id:
            missing.append("base_unit_id")
        if self.is_meat and not self.species_id:
            missing.append("species_id")
        if not self.category_id:
            missing.append("category_id")
        return missing

    def _require_meat_species(self) -> None:
        if self.is_meat and not self.species_id:
            raise SpeciesRequiredError(
                f"El tipo cárnico {self.product_type.value} requiere especie (§11)")

    # ── transiciones de ciclo de vida (§10) ──────────────────────────────
    def _transition(self, target: LifecycleStatus) -> None:
        if not can_transition(self.lifecycle_status, target):
            raise InvalidProductStateError(
                f"Transición no permitida: {self.lifecycle_status.value} → {target.value}")
        self.lifecycle_status = target
        self.updated_at = _now()

    def submit(self) -> None:
        self._require_meat_species()
        self._transition(LifecycleStatus.UNDER_REVIEW)

    def activate(self) -> None:
        self._require_meat_species()
        missing = self.missing_activation_data()
        if missing:
            raise ProductIncompleteError(
                "No se puede activar; faltan datos maestros: " + ", ".join(missing))
        self._transition(LifecycleStatus.ACTIVE)
        self.activated_at = self.activated_at or _now()

    def block(self) -> None:
        self._transition(LifecycleStatus.BLOCKED)

    def unblock(self) -> None:
        # BLOCKED → ACTIVE reutiliza la validación de activación
        if self.lifecycle_status is not LifecycleStatus.BLOCKED:
            raise InvalidProductStateError("Sólo un producto BLOCKED puede desbloquearse")
        self.activate()

    def deactivate(self) -> None:
        self._transition(LifecycleStatus.INACTIVE)

    def discontinue(self) -> None:
        self._transition(LifecycleStatus.DISCONTINUED)
        self.discontinued_at = _now()

    def archive(self) -> None:
        self._transition(LifecycleStatus.ARCHIVED)

    def is_active(self) -> bool:
        return self.lifecycle_status is LifecycleStatus.ACTIVE

    def is_sellable_now(self) -> bool:
        """POS/Ventas: sólo productos ACTIVE, vendibles y no internos (§33)."""
        return self.is_active() and self.sellable and not self.internal_only
