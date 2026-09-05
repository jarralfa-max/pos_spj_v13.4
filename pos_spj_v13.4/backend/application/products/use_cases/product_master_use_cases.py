"""Canonical product-master use cases (P0-01/02/05 — dominio + autorización).

El alta/edición del maestro construye y valida la **entidad `Product`** (VOs
`ProductCode`/`ProductName`/`ProductType`, política de creación, invariantes de
capacidad e interno) antes de persistir — nunca escribe un dict crudo. Toda
operación exige autorización (`ProductsAuthorizationPolicy.require`). El alta nace
siempre en **DRAFT**; el estado sólo cambia por los casos de uso de ciclo de vida
(no por el update). Sin precio/existencia (viven en Pricing/Inventory).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
    UpdateProductMasterCommand,
)
from backend.application.products.notification_handlers.dispatch import (
    dispatch_product_alerts,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.unit_catalog_query_service import (
    UnitCatalogQueryService,
)
from backend.domain.products.entities.product import Product
from backend.domain.products.enums import LifecycleStatus, ProductType
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.policies.product_creation_policy import validate_creation
from backend.infrastructure.db.repositories.products.product_master_repository import (
    ProductMasterRepository,
)

logger = logging.getLogger("spj.products.master_use_cases")

_FLAG_FIELDS = (
    "sellable", "purchasable", "inventory_managed", "producible", "internal_only",
    "recipe_allowed", "bundle_allowed", "lot_controlled", "expiration_controlled",
    "catch_weight_enabled", "quality_controlled", "traceability_required",
)


@dataclass(frozen=True)
class ProductMasterResult:
    success: bool
    product_id: str | None
    message: str


def _normalized(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _entity_row(product: Product) -> dict:
    row = {
        "id": product.id, "code": product.code.value, "name": product.name.value,
        "name_normalized": _normalized(product.name.value),
        "short_name": product.short_name, "description": product.description,
        "product_type": product.product_type.value,
        "lifecycle_status": product.lifecycle_status.value,
        "category_id": product.category_id, "brand_id": product.brand_id,
        "species_id": product.species_id, "internal_stage": product.internal_stage.value,
        "base_unit_id": product.base_unit_id, "created_by": product.created_by,
    }
    row.update({f: getattr(product, f) for f in _FLAG_FIELDS})
    return row


def _build_entity(command, *, product_id: str, lifecycle: LifecycleStatus,
                  code: str, internal_stage: str | None = None) -> Product:
    """Construye la entidad (VOs validan código/nombre/tipo) y corre la política de
    creación. Lanza ProductsDomainError si algún invariante falla.

    ``internal_stage``: en alta usa el del command (puede nacer WIP); en edición
    el caller debe pasar el valor YA EXISTENTE (P0-01: la edición no cambia etapa,
    igual que no cambia lifecycle_status — una transición de etapa real exige su
    propio caso de uso, nunca un efecto colateral de editar nombre/código).
    """
    ptype = ProductType(command.product_type)
    validate_creation(
        product_type=ptype, base_unit_id=command.base_unit_id,
        species_id=command.species_id, sellable=bool(command.sellable),
        internal_only=bool(command.internal_only))
    flags = {f: bool(getattr(command, f)) for f in _FLAG_FIELDS}
    stage = internal_stage if internal_stage is not None else command.internal_stage
    return Product(
        id=product_id, code=code, name=command.name, product_type=ptype,
        base_unit_id=command.base_unit_id, lifecycle_status=lifecycle,
        internal_stage=stage,
        short_name=command.short_name, description=command.description,
        category_id=command.category_id, brand_id=command.brand_id,
        species_id=command.species_id, created_by=command.user_id, **flags)


class CreateProductMasterUseCase:
    name = "CreateProductMasterUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None, *,
                 notification_service=None, notify_recipients: list[str] | None = None
                 ) -> None:
        self._conn = connection
        self._repo = ProductMasterRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()
        # PROD-16: opcional, no-op salvo que el caller provea ambos — ver
        # notification_handlers/dispatch.py.
        self._notification_service = notification_service
        self._notify_recipients = notify_recipients

    def execute(self, command: CreateProductMasterCommand) -> ProductMasterResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.CREATE)
        # P0-04: asignar el código a mano exige PRODUCTS_OVERRIDE_CODE (fail-closed,
        # fuera del try de dominio para que la denegación se propague, no se degrade).
        code_overridden = not command.auto_generate_code
        if code_overridden:
            self._auth.require(command.user_id or "", ProductPermissions.OVERRIDE_CODE)
        if not UnitCatalogQueryService(self._conn).unit_exists(command.base_unit_id):
            return ProductMasterResult(
                False, None, "La unidad base debe ser una unidad válida del catálogo")
        from backend.shared.ids import new_uuid
        product_id = new_uuid()
        try:
            # P0-04: código automático (reserva transaccional) o manual (ya autorizado).
            if command.auto_generate_code:
                from backend.application.products.queries.product_code_query_service import (  # noqa: E501
                    reserve_next_code,
                )
                code = reserve_next_code(self._conn, product_type=command.product_type,
                                         category_id=command.category_id)
            else:
                code = command.code
            if self._repo.code_exists(code):
                _rollback(self._conn)
                return ProductMasterResult(False, None, f"El código '{code}' ya existe")
            # P0-01: el alta nace SIEMPRE en DRAFT (se ignora cualquier estado enviado).
            product = _build_entity(command, product_id=product_id,
                                    lifecycle=LifecycleStatus.DRAFT, code=code)
        except ProductsDomainError as exc:
            _rollback(self._conn)
            return ProductMasterResult(False, None, str(exc))
        try:
            self._repo.create(_entity_row(product))
            if code_overridden:
                _audit_code_override(self._conn, product_id, code, command)
            record_product_audit_entry(
                self._conn, action="PRODUCT_CREATED", entity_id=product_id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"code": code, "name": command.name,
                       "product_type": command.product_type})
            _enqueue_outbox(self._conn, ProductEvents.PRODUCT_CREATED, command,
                            product_id, code=code)
            dispatch_product_alerts(
                self._conn, product, notification_service=self._notification_service,
                notify_recipients=self._notify_recipients,
                operation_id=command.operation_id)
            self._conn.commit()
        except Exception:
            _rollback(self._conn)
            logger.exception("create product master failed op=%s", command.operation_id)
            raise
        return ProductMasterResult(True, product_id, "PRODUCT_CREATED")


class UpdateProductMasterUseCase:
    name = "UpdateProductMasterUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None, *,
                 notification_service=None, notify_recipients: list[str] | None = None
                 ) -> None:
        self._conn = connection
        self._repo = ProductMasterRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()
        self._notification_service = notification_service
        self._notify_recipients = notify_recipients

    def execute(self, command: UpdateProductMasterCommand) -> ProductMasterResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EDIT)
        existing = self._repo.get(command.product_id)
        if existing is None:
            return ProductMasterResult(False, None, "El producto no existe")
        if not UnitCatalogQueryService(self._conn).unit_exists(command.base_unit_id):
            return ProductMasterResult(
                False, None, "La unidad base debe ser una unidad válida del catálogo")
        if self._repo.code_exists(command.code, exclude_id=command.product_id):
            return ProductMasterResult(False, None, f"El código '{command.code}' ya existe")
        # P0-01: el update NO cambia el estado (eso es de los use cases de ciclo de
        # vida); se conserva el lifecycle actual y se revalidan los invariantes.
        current = LifecycleStatus(existing["lifecycle_status"])
        try:
            product = _build_entity(
                command, product_id=command.product_id, lifecycle=current,
                code=command.code,
                internal_stage=existing.get("internal_stage") or "NONE")
        except ProductsDomainError as exc:
            return ProductMasterResult(False, None, str(exc))
        try:
            self._repo.update(command.product_id, _entity_row(product))
            record_product_audit_entry(
                self._conn, action="PRODUCT_UPDATED", entity_id=command.product_id,
                user_id=command.user_id, operation_id=command.operation_id,
                before={"code": existing.get("code"), "name": existing.get("name")},
                after={"code": command.code, "name": command.name})
            _enqueue_outbox(self._conn, ProductEvents.PRODUCT_UPDATED, command,
                            command.product_id, code=command.code)
            dispatch_product_alerts(
                self._conn, product, notification_service=self._notification_service,
                notify_recipients=self._notify_recipients,
                operation_id=command.operation_id)
            self._conn.commit()
        except Exception:
            _rollback(self._conn)
            logger.exception("update product master failed op=%s", command.operation_id)
            raise
        return ProductMasterResult(True, command.product_id, "PRODUCT_UPDATED")


# ── helpers compartidos ──────────────────────────────────────────────────────
def _rollback(conn) -> None:
    rb = getattr(conn, "rollback", None)
    if rb is not None:
        rb()


def _audit_code_override(conn, product_id: str, code: str, command) -> None:
    """P0-04: registra en auditoría toda asignación MANUAL de código."""
    record_product_audit_entry(
        conn, action="CODE_OVERRIDE", entity_id=product_id, user_id=command.user_id,
        operation_id=command.operation_id, after={"code": code},
        reason="Código asignado manualmente", source="product_master")


def _enqueue_outbox(conn, event_name: str, command, product_id: str,
                    *, code: str | None = None) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = json.dumps({"event_id": event_id, "event_name": event_name,
                          "operation_id": command.operation_id, "entity_id": product_id,
                          "product_id": product_id,
                          "code": code if code is not None else command.code,
                          "name": command.name, "product_type": command.product_type})
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, product_id, payload))
