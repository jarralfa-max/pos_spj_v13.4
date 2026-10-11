"""Presenter del catálogo externo (PROD-22, §15).

Buscar en una fuente externa deja los resultados en revisión; aprobar, rechazar e
importar son pasos separados (y quien trajo el registro no lo aprueba, §39). La
búsqueda sale a internet (Open Food Facts): un fallo de red se informa en la
pantalla en vez de reventar.
"""

from __future__ import annotations

import logging

from backend.application.products.permissions import ProductPermissions

logger = logging.getLogger("spj.products.external_presenter")

STATUS_ES = {"PENDING_REVIEW": "Pendiente de revisión", "MATCHED": "Coincide con un producto",
             "APPROVED": "Aprobado", "REJECTED": "Rechazado", "IMPORTED": "Importado"}


class ExternalCatalogPresenter:
    def __init__(self, *, read_factory, write_factory=None, has_permission=None,
                 session=None) -> None:
        self._read = read_factory
        self._write = write_factory
        self._has = has_permission
        self._session = session

    def _allowed(self, code: str) -> bool:
        if self._write is None:
            return False
        return True if self._has is None else bool(self._has(code))

    @property
    def can_search(self) -> bool:
        return self._allowed(ProductPermissions.EXTERNAL_SEARCH)

    @property
    def can_review(self) -> bool:
        return self._allowed(ProductPermissions.EXTERNAL_REVIEW)

    @property
    def can_approve(self) -> bool:
        return self._allowed(ProductPermissions.EXTERNAL_APPROVE)

    @property
    def can_import(self) -> bool:
        return self._allowed(ProductPermissions.IMPORT_EXECUTE)

    def sources(self) -> list[dict]:
        return self._read().sources()

    def records(self, status: str | None = None) -> list[dict]:
        return self._read().records(status=status)

    def search(self, *, source_id: str, query: str) -> tuple[bool, str]:
        from backend.application.products.commands.product_external_catalog_commands import (
            SearchExternalCatalogCommand,
        )
        ok, message, result = self._run("search", lambda op, user: SearchExternalCatalogCommand(
            operation_id=op, source_id=source_id, query=query, user_id=user))
        if ok and result is not None:
            found = len(result.record_ids)
            return True, (f"{found} resultado(s) en revisión." if found
                          else "La fuente no encontró nada con ese texto o código.")
        return ok, message

    def approve(self, record_id: str) -> tuple[bool, str]:
        from backend.application.products.commands.product_external_catalog_commands import (
            ApproveExternalRecordCommand,
        )
        return self._run("approve", lambda op, user: ApproveExternalRecordCommand(
            operation_id=op, record_id=record_id, user_id=user))[:2]

    def reject(self, record_id: str) -> tuple[bool, str]:
        from backend.application.products.commands.product_external_catalog_commands import (
            RejectExternalRecordCommand,
        )
        return self._run("reject", lambda op, user: RejectExternalRecordCommand(
            operation_id=op, record_id=record_id, user_id=user))[:2]

    def import_record(self, *, record_id: str, product_type: str, base_unit_id: str,
                      category_id: str | None) -> tuple[bool, str]:
        from backend.application.products.commands.product_external_catalog_commands import (
            ImportExternalRecordCommand,
        )
        return self._run("import", lambda op, user: ImportExternalRecordCommand(
            operation_id=op, record_id=record_id, user_id=user, product_type=product_type,
            base_unit_id=base_unit_id, category_id=category_id))[:2]

    def _run(self, action: str, build):
        if self._write is None:
            return False, "Sin permisos para el catálogo externo", None
        from backend.shared.ids import new_uuid
        user_id = getattr(self._session, "user_id", None)
        try:
            result = self._write()[action].execute(build(new_uuid(), user_id))
        except Exception as exc:  # noqa: BLE001 — red, permiso o segregación: a la pantalla
            logger.exception("Catálogo externo: %s falló", action)
            return False, f"Error: {exc}", None
        return bool(result.success), result.message, result
