"""Use cases de la galería de imágenes de producto (P1 + PROD-21).

Agregar, marcar como principal, eliminar, quitar el fondo y restaurar el
original. Toda mutación exige ``PRODUCTS_IMAGES_MANAGE`` (fail-closed en
producción) y mantiene el invariante "exactamente una principal por producto": la
primera imagen nace principal; marcar otra desmarca la anterior; al eliminar la
principal se promueve otra. El caso de uso es dueño de la transacción, deja
rastro en ``product_audit_log`` y emite un evento al outbox.

PROD-21: con un ``ProductImageStorage`` el archivo elegido se COPIA a la carpeta
de la aplicación (antes se guardaba la ruta del escritorio del usuario y la
tarjeta del POS quedaba sin imagen al mover el archivo). Los archivos se borran
sólo DESPUÉS del commit, y sólo los de la carpeta administrada.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_image_commands import (
    AddProductImageCommand,
    RemoveImageBackgroundCommand,
    RemoveProductImageCommand,
    RestoreImageBackgroundCommand,
    SetPrimaryImageCommand,
)
from backend.application.products.media.ports import BackgroundRemover, ProductImageStorage
from backend.application.products.permissions import ProductPermissions
from backend.application.security.unwired_policy import unwired
from backend.domain.products.entities.product_image import ProductImage
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import (
    ProductImageProcessingError,
    ProductsDomainError,
)
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
                 authorization: ProductsAuthorizationPolicy | None = None,
                 storage: ProductImageStorage | None = None) -> None:
        self._conn = connection
        self._repo = ProductImageRepository(connection)
        self._auth = authorization or unwired(ProductsAuthorizationPolicy)
        self._storage = storage

    def _require(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.IMAGES_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _discard(self, *uris: str | None) -> None:
        if self._storage is None:
            return
        for uri in uris:
            self._storage.discard(uri)

    def _audit(self, action: str, command, image: ProductImage, *,
               before: dict | None, after: dict | None) -> None:
        record_product_audit_entry(
            self._conn, action=action, entity_id=image.product_id,
            user_id=command.user_id or "", operation_id=command.operation_id,
            before=before, after=after)


def _snapshot(image: ProductImage) -> dict:
    return {"image_id": image.id, "uri": image.uri, "source_uri": image.source_uri,
            "is_primary": image.is_primary,
            "background_removed": image.background_removed}


class AddProductImageUseCase(_BaseImageUseCase):
    name = "AddProductImageUseCase"

    def execute(self, command: AddProductImageCommand) -> ImageResult:
        command.validate()
        self._require(command.user_id)
        uri = command.uri
        if self._storage is not None:
            try:
                uri = self._storage.import_original(command.uri)
            except ProductImageProcessingError as exc:
                return ImageResult(False, None, str(exc))
        # La primera imagen del producto siempre nace principal.
        first = self._repo.count_for_product(command.product_id) == 0
        make_primary = bool(command.make_primary) or first
        from backend.shared.ids import new_uuid
        image_id = new_uuid()
        try:
            image = ProductImage(id=image_id, product_id=command.product_id,
                                 uri=uri, alt_text=command.alt_text,
                                 is_primary=make_primary)
            object.__setattr__(image, "created_by", command.user_id)
        except ProductsDomainError as exc:
            self._discard(uri if uri != command.uri else None)
            return ImageResult(False, None, str(exc))
        try:
            if make_primary:
                self._repo.clear_primary(command.product_id)
            self._repo.add(image)
            self._audit("PRODUCT_IMAGE_ADDED", command, image,
                        before=None, after=_snapshot(image))
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_ADDED, command,
                  entity_id=image_id,
                  extra={"product_id": command.product_id, "is_primary": make_primary})
            self._conn.commit()
        except Exception:
            self._rollback()
            self._discard(uri if uri != command.uri else None)
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
            before = _snapshot(image)
            self._repo.clear_primary(image.product_id)
            self._repo.set_primary(command.image_id)
            image.is_primary = True
            self._audit("PRODUCT_IMAGE_PRIMARY_SET", command, image,
                        before=before, after=_snapshot(image))
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
            self._audit("PRODUCT_IMAGE_REMOVED", command, image,
                        before=_snapshot(image), after=None)
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_REMOVED, command,
                  entity_id=command.image_id,
                  extra={"product_id": image.product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("remove image failed op=%s", command.operation_id)
            raise
        self._discard(image.uri, image.source_uri)
        return ImageResult(True, command.image_id, "PRODUCT_IMAGE_REMOVED")


class RemoveImageBackgroundUseCase(_BaseImageUseCase):
    """PROD-21: genera la versión sin fondo y la deja como la que se muestra."""

    name = "RemoveImageBackgroundUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None,
                 storage: ProductImageStorage | None = None,
                 remover: BackgroundRemover | None = None) -> None:
        super().__init__(connection, authorization, storage)
        self._remover = remover

    def execute(self, command: RemoveImageBackgroundCommand) -> ImageResult:
        command.validate()
        self._require(command.user_id)
        if self._storage is None or self._remover is None:
            return ImageResult(False, None, "Quitar el fondo no está disponible")
        image = self._repo.get(command.image_id)
        if image is None:
            return ImageResult(False, None, "La imagen no existe")
        if image.background_removed:
            return ImageResult(False, image.id, "La imagen ya no tiene fondo")
        source = image.original_uri
        if not self._storage.is_local_file(source):
            return ImageResult(False, image.id,
                               "La imagen original no está en este equipo; "
                               "vuelve a agregarla.")
        target = self._storage.new_processed_path()
        try:
            self._remover.remove_background(source, target)
        except ProductImageProcessingError as exc:
            self._discard(target)
            return ImageResult(False, image.id, str(exc))
        try:
            before = _snapshot(image)
            image.mark_background_removed(target)
            self._repo.save_rendition(image)
            self._audit("PRODUCT_IMAGE_BACKGROUND_REMOVED", command, image,
                        before=before, after=_snapshot(image))
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_BACKGROUND_REMOVED, command,
                  entity_id=image.id, extra={"product_id": image.product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            self._discard(target)
            logger.exception("remove background failed op=%s", command.operation_id)
            raise
        return ImageResult(True, image.id, "PRODUCT_IMAGE_BACKGROUND_REMOVED")


class RestoreImageBackgroundUseCase(_BaseImageUseCase):
    """PROD-21: vuelve a mostrar la foto original."""

    name = "RestoreImageBackgroundUseCase"

    def execute(self, command: RestoreImageBackgroundCommand) -> ImageResult:
        command.validate()
        self._require(command.user_id)
        image = self._repo.get(command.image_id)
        if image is None:
            return ImageResult(False, None, "La imagen no existe")
        if not image.background_removed:
            return ImageResult(False, image.id, "La imagen conserva su fondo original")
        try:
            before = _snapshot(image)
            processed = image.restore_original()
            self._repo.save_rendition(image)
            self._audit("PRODUCT_IMAGE_BACKGROUND_RESTORED", command, image,
                        before=before, after=_snapshot(image))
            _emit(self._conn, ProductEvents.PRODUCT_IMAGE_BACKGROUND_RESTORED, command,
                  entity_id=image.id, extra={"product_id": image.product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("restore background failed op=%s", command.operation_id)
            raise
        self._discard(processed)
        return ImageResult(True, image.id, "PRODUCT_IMAGE_BACKGROUND_RESTORED")


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
