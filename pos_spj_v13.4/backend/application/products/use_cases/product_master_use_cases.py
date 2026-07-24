"""Canonical product-master use cases (PROD-19 paso 7b — alta/edición born-clean).

Create/Update del maestro `products` (UUIDv7). Validan el comando, garantizan la
unicidad de `code`, normalizan el nombre, escriben vía `ProductMasterRepository` y
emiten `PRODUCT_CREATED`/`PRODUCT_UPDATED` al `product_outbox`. Atómicos (una
transacción o ninguna). Sin precio/existencia (viven en Pricing/Inventory).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
    UpdateProductMasterCommand,
)
from backend.domain.products.events import ProductEvents
from backend.infrastructure.db.repositories.products.product_master_repository import (
    ProductMasterRepository,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.products.master_use_cases")

_MASTER_FIELDS = (
    "code", "name", "short_name", "description", "product_type", "lifecycle_status",
    "category_id", "species_id", "base_unit_id", "sellable", "purchasable",
    "inventory_managed", "producible", "internal_only", "recipe_allowed",
    "bundle_allowed", "lot_controlled", "expiration_controlled", "catch_weight_enabled",
    "quality_controlled", "traceability_required",
)


@dataclass(frozen=True)
class ProductMasterResult:
    success: bool
    product_id: str | None
    message: str


def _normalized(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _payload(command, product_id: str) -> dict:
    return {f: getattr(command, f) for f in _MASTER_FIELDS}


class CreateProductMasterUseCase:
    name = "CreateProductMasterUseCase"

    def __init__(self, connection) -> None:
        self._conn = connection
        self._repo = ProductMasterRepository(connection)

    def execute(self, command: CreateProductMasterCommand) -> ProductMasterResult:
        command.validate()
        if self._repo.code_exists(command.code):
            return ProductMasterResult(False, None, f"El código '{command.code}' ya existe")
        product_id = new_uuid()
        data = {"id": product_id, "name_normalized": _normalized(command.name),
                "created_by": command.user_id, **_payload(command, product_id)}
        try:
            self._repo.create(data)
            self._enqueue(ProductEvents.PRODUCT_CREATED, command, product_id)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create product master failed op=%s", command.operation_id)
            raise
        return ProductMasterResult(True, product_id, "PRODUCT_CREATED")

    def _enqueue(self, event_name, command, product_id):
        _enqueue_outbox(self._conn, event_name, command, product_id)

    def _rollback(self):
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


class UpdateProductMasterUseCase:
    name = "UpdateProductMasterUseCase"

    def __init__(self, connection) -> None:
        self._conn = connection
        self._repo = ProductMasterRepository(connection)

    def execute(self, command: UpdateProductMasterCommand) -> ProductMasterResult:
        command.validate()
        if self._repo.get(command.product_id) is None:
            return ProductMasterResult(False, None, "El producto no existe")
        if self._repo.code_exists(command.code, exclude_id=command.product_id):
            return ProductMasterResult(False, None, f"El código '{command.code}' ya existe")
        data = {"name_normalized": _normalized(command.name),
                **_payload(command, command.product_id)}
        try:
            self._repo.update(command.product_id, data)
            _enqueue_outbox(self._conn, ProductEvents.PRODUCT_UPDATED, command,
                            command.product_id)
            self._conn.commit()
        except Exception:
            rb = getattr(self._conn, "rollback", None)
            if rb is not None:
                rb()
            logger.exception("update product master failed op=%s", command.operation_id)
            raise
        return ProductMasterResult(True, command.product_id, "PRODUCT_UPDATED")


def _enqueue_outbox(conn, event_name: str, command, product_id: str) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = json.dumps({"event_id": event_id, "event_name": event_name,
                          "operation_id": command.operation_id, "entity_id": product_id,
                          "product_id": product_id, "code": command.code,
                          "name": command.name, "product_type": command.product_type})
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, product_id, payload))
