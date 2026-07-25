"""Use cases del árbol de categorías de producto (P1-01).

Alta, edición, movimiento (re-parent) y activación/desactivación. Toda mutación
exige ``PRODUCTS_CATEGORIES_MANAGE`` (fail-closed en producción), valida los
invariantes de jerarquía (unicidad de código, anti-ciclo, profundidad máxima) y
emite un evento al outbox. El caso de uso es dueño de la transacción; al mover una
rama se reescriben las rutas de todos los descendientes en la misma tx.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_category_commands import (
    CreateCategoryCommand,
    MoveCategoryCommand,
    SetCategoryActiveCommand,
    UpdateCategoryCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.product_category import (
    ProductCategory,
    normalize_name,
)
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.policies.product_category_hierarchy_policy import (
    child_depth,
    child_path,
    ensure_acyclic_reparent,
    ensure_within_depth,
)
from backend.infrastructure.db.repositories.products.category_repository import (
    ProductCategoryRepository,
)

logger = logging.getLogger("spj.products.category_use_cases")


@dataclass(frozen=True)
class CategoryResult:
    success: bool
    category_id: str | None
    message: str


class _BaseCategoryUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductCategoryRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()

    def _require_manage(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.CATEGORIES_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _emit(self, event_name: str, command, category_id: str, **extra) -> None:
        _enqueue_outbox(self._conn, event_name, command, category_id, extra)


class CreateProductCategoryUseCase(_BaseCategoryUseCase):
    name = "CreateProductCategoryUseCase"

    def execute(self, command: CreateCategoryCommand) -> CategoryResult:
        command.validate()
        self._require_manage(command.user_id)
        code = (command.code or "").strip().upper()
        if self._repo.code_exists(code):
            return CategoryResult(False, None, f"El código '{code}' ya existe")
        parent = None
        if command.parent_id:
            parent = self._repo.get(command.parent_id)
            if parent is None:
                return CategoryResult(False, None, "La categoría padre no existe")
        from backend.shared.ids import new_uuid
        category_id = new_uuid()
        depth = child_depth(parent.depth if parent else None)
        try:
            ensure_within_depth(depth)
            entity = ProductCategory(
                id=category_id, code=code, name=command.name,
                parent_id=command.parent_id, depth=depth,
                path=child_path(parent.path if parent else None, category_id),
                sort_order=int(command.sort_order))
            object.__setattr__(entity, "created_by", command.user_id)
        except ProductsDomainError as exc:
            return CategoryResult(False, None, str(exc))
        try:
            self._repo.create(entity)
            self._emit(ProductEvents.PRODUCT_CATEGORY_CREATED, command, category_id,
                       code=code, name=command.name, parent_id=command.parent_id)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create category failed op=%s", command.operation_id)
            raise
        return CategoryResult(True, category_id, "PRODUCT_CATEGORY_CREATED")


class UpdateProductCategoryUseCase(_BaseCategoryUseCase):
    name = "UpdateProductCategoryUseCase"

    def execute(self, command: UpdateCategoryCommand) -> CategoryResult:
        command.validate()
        self._require_manage(command.user_id)
        existing = self._repo.get(command.category_id)
        if existing is None:
            return CategoryResult(False, None, "La categoría no existe")
        code = (command.code or "").strip().upper()
        if self._repo.code_exists(code, exclude_id=command.category_id):
            return CategoryResult(False, None, f"El código '{code}' ya existe")
        try:
            # Revalida código/nombre reconstruyendo la entidad (VOs del dominio).
            ProductCategory(id=command.category_id, code=code, name=command.name,
                            parent_id=existing.parent_id, depth=existing.depth,
                            path=existing.path)
        except ProductsDomainError as exc:
            return CategoryResult(False, None, str(exc))
        try:
            self._repo.update_fields(
                command.category_id, code=code, name=command.name.strip(),
                name_normalized=normalize_name(command.name),
                sort_order=int(command.sort_order))
            self._emit(ProductEvents.PRODUCT_CATEGORY_UPDATED, command,
                       command.category_id, code=code, name=command.name)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update category failed op=%s", command.operation_id)
            raise
        return CategoryResult(True, command.category_id, "PRODUCT_CATEGORY_UPDATED")


class MoveProductCategoryUseCase(_BaseCategoryUseCase):
    name = "MoveProductCategoryUseCase"

    def execute(self, command: MoveCategoryCommand) -> CategoryResult:
        command.validate()
        self._require_manage(command.user_id)
        category = self._repo.get(command.category_id)
        if category is None:
            return CategoryResult(False, None, "La categoría no existe")
        new_parent = None
        if command.new_parent_id:
            new_parent = self._repo.get(command.new_parent_id)
            if new_parent is None:
                return CategoryResult(False, None, "La categoría padre no existe")
        old_path = category.path
        new_depth = child_depth(new_parent.depth if new_parent else None)
        new_path = child_path(new_parent.path if new_parent else None, category.id)
        try:
            ensure_acyclic_reparent(
                category_id=category.id, category_path=category.path,
                new_parent_id=command.new_parent_id,
                new_parent_path=new_parent.path if new_parent else None)
            # La rama más profunda del subárbol no debe rebasar el máximo.
            deepest = max((d.depth for d in self._repo.descendants(category)),
                          default=category.depth)
            ensure_within_depth(new_depth + (deepest - category.depth))
        except ProductsDomainError as exc:
            return CategoryResult(False, None, str(exc))
        try:
            self._repo.reparent(category.id, parent_id=command.new_parent_id,
                                path=new_path, depth=new_depth)
            self._repo.rewrite_subtree(old_prefix=old_path, new_prefix=new_path,
                                       depth_delta=new_depth - category.depth)
            self._emit(ProductEvents.PRODUCT_CATEGORY_MOVED, command, category.id,
                       new_parent_id=command.new_parent_id)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("move category failed op=%s", command.operation_id)
            raise
        return CategoryResult(True, category.id, "PRODUCT_CATEGORY_MOVED")


class SetProductCategoryActiveUseCase(_BaseCategoryUseCase):
    name = "SetProductCategoryActiveUseCase"

    def execute(self, command: SetCategoryActiveCommand) -> CategoryResult:
        command.validate()
        self._require_manage(command.user_id)
        category = self._repo.get(command.category_id)
        if category is None:
            return CategoryResult(False, None, "La categoría no existe")
        if not command.active and self._repo.has_active_children(command.category_id):
            return CategoryResult(
                False, None,
                "No se puede desactivar una categoría con subcategorías activas")
        try:
            self._repo.set_active(command.category_id, command.active)
            if not command.active:
                self._emit(ProductEvents.PRODUCT_CATEGORY_DEACTIVATED, command,
                           command.category_id, active=False)
            else:
                self._emit(ProductEvents.PRODUCT_CATEGORY_UPDATED, command,
                           command.category_id, active=True)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active category failed op=%s", command.operation_id)
            raise
        msg = "PRODUCT_CATEGORY_UPDATED" if command.active \
            else "PRODUCT_CATEGORY_DEACTIVATED"
        return CategoryResult(True, command.category_id, msg)


def _enqueue_outbox(conn, event_name: str, command, category_id: str,
                    extra: dict) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
               "operation_id": command.operation_id, "entity_id": category_id,
               "category_id": category_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, category_id,
         json.dumps(payload)))
