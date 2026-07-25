"""Use cases del catálogo de atributos de producto y sus opciones (P1-03).

Alta/edición/activación de atributos y alta/edición de opciones enumeradas. Toda
mutación exige ``PRODUCTS_ATTRIBUTES_MANAGE`` (fail-closed en producción), valida
unicidad de código y los invariantes de dominio (sólo los atributos LISTA admiten
opciones), y emite un evento al outbox. El caso de uso es dueño de la transacción.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_attribute_commands import (
    AddAttributeOptionCommand,
    CreateAttributeCommand,
    SetAttributeActiveCommand,
    UpdateAttributeCommand,
    UpdateAttributeOptionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.product_attribute import (
    AttributeOption,
    ProductAttribute,
    normalize_name,
)
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.infrastructure.db.repositories.products.attribute_repository import (
    ProductAttributeRepository,
)

logger = logging.getLogger("spj.products.attribute_use_cases")


@dataclass(frozen=True)
class AttributeResult:
    success: bool
    entity_id: str | None
    message: str


class _BaseAttributeUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductAttributeRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()

    def _require_manage(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.ATTRIBUTES_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _emit(self, event_name: str, command, entity_id: str, **extra) -> None:
        _enqueue_outbox(self._conn, event_name, command, entity_id, extra)


class CreateProductAttributeUseCase(_BaseAttributeUseCase):
    name = "CreateProductAttributeUseCase"

    def execute(self, command: CreateAttributeCommand) -> AttributeResult:
        command.validate()
        self._require_manage(command.user_id)
        code = (command.code or "").strip().upper()
        if self._repo.code_exists(code):
            return AttributeResult(False, None, f"El código '{code}' ya existe")
        from backend.shared.ids import new_uuid
        attribute_id = new_uuid()
        try:
            attribute = ProductAttribute(id=attribute_id, code=code, name=command.name,
                                         data_type=command.data_type)
            object.__setattr__(attribute, "created_by", command.user_id)
        except ProductsDomainError as exc:
            return AttributeResult(False, None, str(exc))
        try:
            self._repo.create(attribute)
            self._emit(ProductEvents.PRODUCT_ATTRIBUTE_CREATED, command, attribute_id,
                       code=code, name=command.name,
                       data_type=attribute.data_type.value)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create attribute failed op=%s", command.operation_id)
            raise
        return AttributeResult(True, attribute_id, "PRODUCT_ATTRIBUTE_CREATED")


class UpdateProductAttributeUseCase(_BaseAttributeUseCase):
    name = "UpdateProductAttributeUseCase"

    def execute(self, command: UpdateAttributeCommand) -> AttributeResult:
        command.validate()
        self._require_manage(command.user_id)
        existing = self._repo.get(command.attribute_id)
        if existing is None:
            return AttributeResult(False, None, "El atributo no existe")
        code = (command.code or "").strip().upper()
        if self._repo.code_exists(code, exclude_id=command.attribute_id):
            return AttributeResult(False, None, f"El código '{code}' ya existe")
        try:
            # Revalida código/nombre; el tipo de dato es inmutable tras el alta.
            ProductAttribute(id=command.attribute_id, code=code, name=command.name,
                             data_type=existing.data_type)
        except ProductsDomainError as exc:
            return AttributeResult(False, None, str(exc))
        try:
            self._repo.update_fields(command.attribute_id, code=code,
                                     name=command.name.strip(),
                                     name_normalized=normalize_name(command.name))
            self._emit(ProductEvents.PRODUCT_ATTRIBUTE_UPDATED, command,
                       command.attribute_id, code=code, name=command.name)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update attribute failed op=%s", command.operation_id)
            raise
        return AttributeResult(True, command.attribute_id, "PRODUCT_ATTRIBUTE_UPDATED")


class SetProductAttributeActiveUseCase(_BaseAttributeUseCase):
    name = "SetProductAttributeActiveUseCase"

    def execute(self, command: SetAttributeActiveCommand) -> AttributeResult:
        command.validate()
        self._require_manage(command.user_id)
        if self._repo.get(command.attribute_id) is None:
            return AttributeResult(False, None, "El atributo no existe")
        try:
            self._repo.set_active(command.attribute_id, command.active)
            event = (ProductEvents.PRODUCT_ATTRIBUTE_UPDATED if command.active
                     else ProductEvents.PRODUCT_ATTRIBUTE_DEACTIVATED)
            self._emit(event, command, command.attribute_id, active=command.active)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active attribute failed op=%s", command.operation_id)
            raise
        msg = "PRODUCT_ATTRIBUTE_UPDATED" if command.active \
            else "PRODUCT_ATTRIBUTE_DEACTIVATED"
        return AttributeResult(True, command.attribute_id, msg)


class AddAttributeOptionUseCase(_BaseAttributeUseCase):
    name = "AddAttributeOptionUseCase"

    def execute(self, command: AddAttributeOptionCommand) -> AttributeResult:
        command.validate()
        self._require_manage(command.user_id)
        attribute = self._repo.get(command.attribute_id)
        if attribute is None:
            return AttributeResult(False, None, "El atributo no existe")
        code = (command.code or "").strip().upper()
        try:
            attribute.ensure_accepts_options()  # sólo LISTA admite opciones
            if self._repo.option_code_exists(command.attribute_id, code):
                return AttributeResult(
                    False, None, f"La opción '{code}' ya existe en este atributo")
            from backend.shared.ids import new_uuid
            option = AttributeOption(id=new_uuid(), attribute_id=command.attribute_id,
                                     code=code, label=command.label,
                                     sort_order=int(command.sort_order))
        except ProductsDomainError as exc:
            return AttributeResult(False, None, str(exc))
        try:
            self._repo.add_option(option)
            self._emit(ProductEvents.PRODUCT_ATTRIBUTE_OPTION_ADDED, command,
                       option.id, attribute_id=command.attribute_id, code=code,
                       label=command.label)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("add option failed op=%s", command.operation_id)
            raise
        return AttributeResult(True, option.id, "PRODUCT_ATTRIBUTE_OPTION_ADDED")


class UpdateAttributeOptionUseCase(_BaseAttributeUseCase):
    name = "UpdateAttributeOptionUseCase"

    def execute(self, command: UpdateAttributeOptionCommand) -> AttributeResult:
        command.validate()
        self._require_manage(command.user_id)
        existing = self._repo.get_option(command.option_id)
        if existing is None:
            return AttributeResult(False, None, "La opción no existe")
        code = (command.code or "").strip().upper()
        if self._repo.option_code_exists(existing.attribute_id, code,
                                         exclude_id=command.option_id):
            return AttributeResult(
                False, None, f"La opción '{code}' ya existe en este atributo")
        try:
            AttributeOption(id=command.option_id, attribute_id=existing.attribute_id,
                            code=code, label=command.label)
        except ProductsDomainError as exc:
            return AttributeResult(False, None, str(exc))
        try:
            self._repo.update_option(command.option_id, code=code,
                                     label=command.label.strip(),
                                     sort_order=int(command.sort_order),
                                     active=bool(command.active))
            self._emit(ProductEvents.PRODUCT_ATTRIBUTE_OPTION_UPDATED, command,
                       command.option_id, code=code, label=command.label)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update option failed op=%s", command.operation_id)
            raise
        return AttributeResult(True, command.option_id,
                               "PRODUCT_ATTRIBUTE_OPTION_UPDATED")


def _enqueue_outbox(conn, event_name: str, command, entity_id: str,
                    extra: dict) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
               "operation_id": command.operation_id, "entity_id": entity_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, entity_id,
         json.dumps(payload)))
