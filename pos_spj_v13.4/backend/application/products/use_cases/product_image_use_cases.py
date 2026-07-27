"""Use cases de la galería de imágenes de producto (P1).

Agregar, marcar como principal y eliminar imágenes. Toda mutación exige
``PRODUCTS_IMAGES_MANAGE`` (fail-closed en producción) y mantiene el invariante
"exactamente una principal por producto": la primera imagen nace principal; marcar
otra desmarca la anterior; al eliminar la principal se promueve otra. El caso de uso
es dueño de la transacción y emite un evento al outbox.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_image_commands import (
    AddProductImageCommand,
    RemoveProductImageCommand,
    SetPrimaryImageCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.product_image import ProductImage
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.infrastructure.db.repositories.products.image_repository import (
    ProductImageRepository,
)

logger = logging.getLogger("spj.products.image_use_cases")


@dataclass(frozen=True)
class ImageResult:
    success: bool
    image_id: str | None
    message: str


class _BaseImageUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductImageRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()

    def _require(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.IMAGES_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


class AddProductImageUseCase(_BaseImageUseCase):
    name = "AddProductImageUseCase"

    def execute(self, command: AddProductImageCommand) -> ImageResult:
        command.validate()
        self._require(command.user_id)
        # La primera imagen del producto siempre nace principal.
        first = self._repo.count_for_product(command.product_id) == 0
        make_primary = bool(command.make_primary) or first
        from backend.shared.ids import new_uuid
        image_id = new_uuid()
        try:
            image = ProductImage(id=image_id, product_id=command.product_id,
                                 uri=command.uri, alt_text=command.alt_text,
                                 is_primary=make_primary)
            object.__setattr__(image, "created_by", command.user_id)
        except ProductsDomainError as exc:
            return ImageResult(False, None, str(exc))
        try:
            if make_primary:
                self._repo.clear_primary(command.product_id)
            self._repo.add(image)
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_ADDED, command,
                  entity_id=image_id,
                  extra={"product_id": command.product_id, "is_primary": make_primary})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("add image failed op=%s", command.operation_id)
            raise
        return ImageResult(True, image_id, "PRODUCT_IMAGE_ADDED")


class SetPrimaryImageUseCase(_BaseImageUseCase):
    name = "SetPrimaryImageUseCase"

    def execute(self, command: SetPrimaryImageCommand) -> ImageResult:
        command.validate()
        self._require(command.user_id)
        image = self._repo.get(command.image_id)
        if image is None:
            return ImageResult(False, None, "La imagen no existe")
        try:
            self._repo.clear_primary(image.product_id)
            self._repo.set_primary(command.image_id)
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_PRIMARY_SET, command,
                  entity_id=command.image_id,
                  extra={"product_id": image.product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set primary image failed op=%s", command.operation_id)
            raise
        return ImageResult(True, command.image_id, "PRODUCT_IMAGE_PRIMARY_SET")


class RemoveProductImageUseCase(_BaseImageUseCase):
    name = "RemoveProductImageUseCase"

    def execute(self, command: RemoveProductImageCommand) -> ImageResult:
        command.validate()
        self._require(command.user_id)
        image = self._repo.get(command.image_id)
        if image is None:
            return ImageResult(False, None, "La imagen no existe")
        try:
            self._repo.remove(command.image_id)
            # Si se elimina la principal, se promueve otra (si queda alguna).
            if image.is_primary:
                promote = self._repo.first_other(image.product_id,
                                                 exclude_id=command.image_id)
                if promote is not None:
                    self._repo.set_primary(promote.id)
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_REMOVED, command,
                  entity_id=command.image_id,
                  extra={"product_id": image.product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("remove image failed op=%s", command.operation_id)
            raise
        return ImageResult(True, command.image_id, "PRODUCT_IMAGE_REMOVED")


def _emit(conn, event_name: str, command, *, entity_id: str, extra: dict) -> None:
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
