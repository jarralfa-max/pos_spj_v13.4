"""Product lifecycle use cases (P0-01/02/05 — transiciones de estado con dominio).

Cada transición del maestro es un caso de uso propio, exige su permiso granular y
delega la regla en la entidad `Product` (tabla de transiciones única). El alta nace
DRAFT; para llegar a ACTIVE hay que pasar por UNDER_REVIEW (submit) y activar
(activate), que además valida completitud y **segregación** (quien crea ≠ quien
activa). Atómicos; emiten el evento canónico al `product_outbox`.
"""

from __future__ import annotations

import json
import logging

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.product import Product
from backend.domain.products.enums import LifecycleStatus, ProductType
from backend.domain.products.internal_enums import InternalStage
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.infrastructure.db.repositories.products.product_master_repository import (
    ProductMasterRepository,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.products.lifecycle")

_FLAG_FIELDS = (
    "sellable", "purchasable", "inventory_managed", "producible", "internal_only",
    "recipe_allowed", "bundle_allowed", "lot_controlled", "expiration_controlled",
    "catch_weight_enabled", "quality_controlled", "traceability_required",
)


def _row_to_entity(row: dict) -> Product:
    flags = {f: bool(row.get(f)) for f in _FLAG_FIELDS}
    return Product(
        id=row["id"], code=row["code"], name=row["name"],
        product_type=ProductType(row["product_type"]),
        base_unit_id=row["base_unit_id"],
        lifecycle_status=LifecycleStatus(row["lifecycle_status"]),
        internal_stage=InternalStage(row.get("internal_stage") or "NONE"),
        short_name=row.get("short_name"), description=row.get("description"),
        category_id=row.get("category_id"), species_id=row.get("species_id"),
        created_by=row.get("created_by"), **flags)


class _LifecycleResult:
    def __init__(self, success: bool, message: str, status: str | None = None):
        self.success = success
        self.message = message
        self.status = status


class _BaseLifecycleUseCase:
    permission: str = ""
    event: str = ""
    transition: str = ""

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductMasterRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def execute(self, *, product_id: str, user_id: str,
                operation_id: str | None = None) -> _LifecycleResult:
        self._auth.require(user_id or "", self.permission)
        row = self._repo.get(product_id)
        if row is None:
            return _LifecycleResult(False, "El producto no existe")
        self._check_extra(row, user_id)
        try:
            product = _row_to_entity(row)
            getattr(product, self.transition)()
        except ProductsDomainError as exc:
            return _LifecycleResult(False, str(exc))
        op = operation_id or new_uuid()
        try:
            self._repo.update_lifecycle(
                product_id, status=product.lifecycle_status.value,
                activated_at=product.activated_at,
                discontinued_at=product.discontinued_at)
            record_product_audit_entry(
                self._conn, action=self.event, entity_id=product_id, user_id=user_id,
                operation_id=op, before={"lifecycle_status": row["lifecycle_status"]},
                after={"lifecycle_status": product.lifecycle_status.value})
            _enqueue(self._conn, self.event, product_id, op, product.lifecycle_status.value)
            self._conn.commit()
        except Exception:
            rb = getattr(self._conn, "rollback", None)
            if rb is not None:
                rb()
            logger.exception("lifecycle %s failed pid=%s", self.transition, product_id)
            raise
        return _LifecycleResult(True, self.event, product.lifecycle_status.value)

    def _check_extra(self, row: dict, user_id: str) -> None:
        pass


class SubmitProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.SUBMIT
    event = "PRODUCT_SUBMITTED"
    transition = "submit"


class ActivateProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.ACTIVATE
    event = ProductEvents.PRODUCT_ACTIVATED
    transition = "activate"

    def _check_extra(self, row: dict, user_id: str) -> None:
        # Segregación (§39): quien creó el producto no puede activarlo (segundo par
        # de ojos). Se evalúa con el permiso de aprobación (APPROVE → CREATE).
        self._auth.ensure_segregation(
            actor_user_id=user_id, creator_user_id=row.get("created_by"),
            approval_permission=ProductPermissions.APPROVE)


class DeactivateProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.DEACTIVATE
    event = ProductEvents.PRODUCT_DEACTIVATED
    transition = "deactivate"


class BlockProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.BLOCK
    event = ProductEvents.PRODUCT_BLOCKED
    transition = "block"


class UnblockProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.ACTIVATE
    event = ProductEvents.PRODUCT_ACTIVATED
    transition = "unblock"


class DiscontinueProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.DISCONTINUE
    event = "PRODUCT_DISCONTINUED"
    transition = "discontinue"


class ArchiveProductUseCase(_BaseLifecycleUseCase):
    permission = ProductPermissions.ARCHIVE
    event = "PRODUCT_ARCHIVED"
    transition = "archive"


def _enqueue(conn, event_name: str, product_id: str, operation_id: str, status: str) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = json.dumps({"event_id": event_id, "event_name": event_name,
                          "operation_id": operation_id, "entity_id": product_id,
                          "product_id": product_id, "lifecycle_status": status})
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, operation_id, product_id, payload))
