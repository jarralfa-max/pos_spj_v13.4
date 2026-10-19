"""Presentador de Logística (integración 32cfbf): catálogo de contenedores y
embarques. Sin SQL ni reglas: lee de `LogisticsContainerQueryService` y muta
por `ContainerCatalogService` (que autoriza, audita y registra la operación)."""

from __future__ import annotations

import logging

from backend.application.logistics.authorization import LogisticsPermissions

logger = logging.getLogger("spj.logistics.presenter")

#: Estados que se pueden fijar desde el catálogo, en el orden del selector.
OPERATIONAL_STATUS_OPTIONS = (
    ("AVAILABLE", "Disponible"), ("CLEANING", "En limpieza"),
    ("MAINTENANCE", "En mantenimiento"), ("QUARANTINED", "En cuarentena"),
    ("RETIRED", "Dar de baja"),
)


class LogisticsPresenter:
    def __init__(self, *, queries, catalog, session_context, labels=None) -> None:
        self._queries = queries
        self._catalog = catalog
        self._labels = labels
        self._session = session_context

    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def can_manage(self) -> bool:
        check = getattr(self._session, "tiene_permiso", None)
        return bool(callable(check) and check(LogisticsPermissions.CONTAINER_MANAGE))

    def can_print(self) -> bool:
        check = getattr(self._session, "tiene_permiso", None)
        return bool(callable(check) and check(LogisticsPermissions.LABEL_PRINT))

    # ── lecturas ────────────────────────────────────────────────────────────
    def containers(self, search: str = "", status: str | None = None) -> list[dict]:
        try:
            return self._queries.containers(search=search, status=status)
        except Exception:
            logger.exception("contenedores no disponibles")
            return []

    def history(self, container_id: str) -> list[dict]:
        try:
            return self._queries.history(container_id)
        except Exception:
            logger.exception("historial no disponible")
            return []

    def shipments(self, search: str = "") -> list[dict]:
        try:
            return self._queries.shipments(search=search)
        except Exception:
            logger.exception("embarques no disponibles")
            return []

    def container_types(self) -> list[tuple[str, str]]:
        try:
            return self._catalog.container_types()
        except Exception:
            logger.exception("tipos de contenedor no disponibles")
            return []

    # ── mutaciones: (ok, mensaje) ───────────────────────────────────────────
    def _run(self, action, success: str, **fields) -> tuple[bool, str, object]:
        try:
            return True, success, action(actor_user_id=self._actor(), **fields)
        except (ValueError, PermissionError) as exc:
            return False, str(exc), None
        except Exception:
            logger.exception("Logística: operación fallida")
            return False, "Error inesperado; revise el log.", None

    def register_type(self, **fields):
        return self._run(self._catalog.register_container_type, "Tipo registrado.", **fields)

    def next_code_preview(self, container_type_id: str | None = None,
                          category: str | None = None) -> str:
        try:
            return self._catalog.next_code_preview(container_type_id, category)
        except Exception:
            logger.exception("vista previa del código no disponible")
            return ""

    def register_container(self, **fields):
        ok, mensaje, resultado = self._run(self._catalog.register_container, "", **fields)
        if ok and resultado:
            codigos = resultado["codes"]
            mensaje = (f"Contenedor {codigos[0]} registrado con su QR."
                       if len(codigos) == 1 else
                       f"{len(codigos)} contenedores registrados: {codigos[0]} a {codigos[-1]}.")
        return ok, mensaje, resultado

    def update_container(self, container_id: str, **fields):
        return self._run(self._catalog.update_container, "Contenedor actualizado.",
                         container_id=container_id, **fields)

    def set_status(self, container_id: str, status: str, reason: str):
        return self._run(self._catalog.set_status, "Estado actualizado.",
                         container_id=container_id, status=status, reason=reason)

    # ── etiquetas QR ────────────────────────────────────────────────────────
    def label_formats(self) -> list[tuple[str, str]]:
        from backend.domain.logistics.labels import ContainerLabelFormat
        return [(f.value, f.label) for f in ContainerLabelFormat]

    def label_preview(self, container_id: str, fmt: str) -> bytes | None:
        from backend.domain.logistics.labels import ContainerLabelFormat
        try:
            return self._labels.preview_png(container_id, ContainerLabelFormat(fmt))
        except Exception:
            logger.exception("vista previa de la etiqueta no disponible")
            return None

    def reprint_codes(self, container_ids) -> list[str]:
        try:
            return self._labels.reprint_codes(container_ids)
        except Exception:
            logger.exception("historial de impresión no disponible")
            return []

    def export_labels_pdf(self, container_ids, fmt: str, copies: int, reason: str,
                          path: str):
        def exportar(*, actor_user_id):
            datos = self._labels.export_pdf(
                actor_user_id=actor_user_id, container_ids=container_ids, fmt=fmt,
                copies=copies, reprint_reason=reason)
            with open(path, "wb") as archivo:
                archivo.write(datos)
            return path
        return self._run(exportar, f"Etiquetas guardadas en {path}.")

    def print_labels_thermal(self, container_ids, copies: int, reason: str):
        return self._run(
            lambda *, actor_user_id: self._labels.print_thermal(
                actor_user_id=actor_user_id, container_ids=container_ids, copies=copies,
                reprint_reason=reason),
            "Etiquetas enviadas a la impresora térmica.")
