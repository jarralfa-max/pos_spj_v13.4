"""Use cases del catálogo de marcas de producto (P1-02).

Alta, edición y activación/desactivación. Toda mutación exige
``PRODUCTS_BRANDS_MANAGE`` (fail-closed en producción), valida unicidad de código y
los invariantes de la entidad ``Brand``, y emite un evento al outbox. El caso de uso
es dueño de la transacción.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_brand_commands import (
    CreateBrandCommand,
    SetBrandActiveCommand,
    UpdateBrandCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.brand import Brand, normalize_name
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.infrastructure.db.repositories.products.brand_repository import (
    ProductBrandRepository,
)

logger = logging.getLogger("spj.products.brand_use_cases")


@dataclass(frozen=True)
class BrandResult:
    success: bool
    brand_id: str | None
    message: str


class _BaseBrandUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductBrandRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()

    def _require_manage(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.BRANDS_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _emit(self, event_name: str, command, brand_id: str, **extra) -> None:
        _enqueue_outbox(self._conn, event_name, command, brand_id, extra)


class CreateProductBrandUseCase(_BaseBrandUseCase):
    name = "CreateProductBrandUseCase"

    def execute(self, command: CreateBrandCommand) -> BrandResult:
        command.validate()
        self._require_manage(command.user_id)
        code = (command.code or "").strip().upper()
        if self._repo.code_exists(code):
            return BrandResult(False, None, f"El código '{code}' ya existe")
        from backend.shared.ids import new_uuid
        brand_id = new_uuid()
        try:
            brand = Brand(id=brand_id, code=code, name=command.name,
                          description=command.description)
            object.__setattr__(brand, "created_by", command.user_id)
        except ProductsDomainError as exc:
            return BrandResult(False, None, str(exc))
        try:
            self._repo.create(brand)
            self._emit(ProductEvents.PRODUCT_BRAND_CREATED, command, brand_id,
                       code=code, name=command.name)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create brand failed op=%s", command.operation_id)
            raise
        return BrandResult(True, brand_id, "PRODUCT_BRAND_CREATED")


class UpdateProductBrandUseCase(_BaseBrandUseCase):
    name = "UpdateProductBrandUseCase"

    def execute(self, command: UpdateBrandCommand) -> BrandResult:
        command.validate()
        self._require_manage(command.user_id)
        existing = self._repo.get(command.brand_id)
        if existing is None:
            return BrandResult(False, None, "La marca no existe")
        code = (command.code or "").strip().upper()
        if self._repo.code_exists(code, exclude_id=command.brand_id):
            return BrandResult(False, None, f"El código '{code}' ya existe")
        try:
            brand = Brand(id=command.brand_id, code=code, name=command.name,
                          description=command.description)
        except ProductsDomainError as exc:
            return BrandResult(False, None, str(exc))
        try:
            self._repo.update_fields(
                command.brand_id, code=code, name=brand.name,
                name_normalized=normalize_name(command.name),
                description=brand.description)
            self._emit(ProductEvents.PRODUCT_BRAND_UPDATED, command,
                       command.brand_id, code=code, name=command.name)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update brand failed op=%s", command.operation_id)
            raise
        return BrandResult(True, command.brand_id, "PRODUCT_BRAND_UPDATED")


class SetProductBrandActiveUseCase(_BaseBrandUseCase):
    name = "SetProductBrandActiveUseCase"

    def execute(self, command: SetBrandActiveCommand) -> BrandResult:
        command.validate()
        self._require_manage(command.user_id)
        if self._repo.get(command.brand_id) is None:
            return BrandResult(False, None, "La marca no existe")
        try:
            self._repo.set_active(command.brand_id, command.active)
            event = (ProductEvents.PRODUCT_BRAND_UPDATED if command.active
                     else ProductEvents.PRODUCT_BRAND_DEACTIVATED)
            self._emit(event, command, command.brand_id, active=command.active)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active brand failed op=%s", command.operation_id)
            raise
        msg = "PRODUCT_BRAND_UPDATED" if command.active \
            else "PRODUCT_BRAND_DEACTIVATED"
        return BrandResult(True, command.brand_id, msg)


def _enqueue_outbox(conn, event_name: str, command, brand_id: str,
                    extra: dict) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
               "operation_id": command.operation_id, "entity_id": brand_id,
               "brand_id": brand_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, brand_id,
         json.dumps(payload)))
