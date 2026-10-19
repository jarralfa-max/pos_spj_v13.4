"""Etiquetas QR de contenedores (2026-10-17).

Antes sólo existía «Reimprimir QR» hacia una impresora térmica enrutada: sin
impresora asignada no había forma de obtener la etiqueta, ni vista previa, ni
etiquetas para impresoras de etiquetas u hojas. Este servicio es la única
puerta:

* `contents` arma lo que lleva cada etiqueta (`ContainerLabelContent`) con el QR
  VIGENTE (firma guardada; reimprimir no cambia la identidad).
* `export_pdf` produce el PDF del formato elegido y registra cada etiqueta y su
  trabajo de impresión (auditoría); `print_thermal` va a la térmica enrutada.
* La PRIMERA impresión no pide motivo; las siguientes son reimpresiones y sí.

El dibujo se inyecta (`renderer`): esta capa no conoce PDF ni ESC/POS.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.logistics.container_catalog import CONTAINER_CATEGORY_ES
from backend.domain.logistics.labels import ContainerLabelContent, ContainerLabelFormat
from backend.shared.ids import new_uuid


class ContainerLabelRenderer(Protocol):
    def pdf(self, contents: list[ContainerLabelContent], fmt: ContainerLabelFormat,
            *, copies: int = 1) -> bytes: ...

    def preview_png(self, content: ContainerLabelContent,
                    fmt: ContainerLabelFormat) -> bytes: ...


class _RecordOnly:
    """Destino del PDF: el archivo lo genera `export_pdf`; aquí sólo se deja
    constancia del trabajo (se marca completado)."""

    def submit(self, job, payload: str) -> None:
        return None


class ContainerLabelService:
    MAX_LABELS = 500

    def __init__(self, logistics_service, queries, renderer: ContainerLabelRenderer) -> None:
        self._logistics = logistics_service
        self._queries = queries
        self._renderer = renderer

    def contents(self, container_ids) -> list[ContainerLabelContent]:
        filas = self._queries.label_rows(container_ids)
        if not filas:
            raise ValueError("Selecciona al menos un contenedor")
        if len(filas) > self.MAX_LABELS:
            raise ValueError(f"Máximo {self.MAX_LABELS} etiquetas por vez")
        dueno = self._queries.owner_name()
        return [ContainerLabelContent(
            container_id=f["id"], code=f["code"], type_name=f["type_name"],
            category_label=CONTAINER_CATEGORY_ES.get(f["category"], f["category"]),
            tare_weight=f["tare_weight"], capacity_weight=f["capacity_weight"],
            owner_name=dueno, qr_payload=self._logistics.label_token(f["id"]),
            qr_version=f["qr_version"]) for f in filas]

    def preview_png(self, container_id: str, fmt: ContainerLabelFormat) -> bytes:
        (content,) = self.contents([container_id])
        return self._renderer.preview_png(
            content, fmt if fmt.is_pdf else ContainerLabelFormat.LABEL_100X50)

    def reprint_codes(self, container_ids) -> list[str]:
        return self._queries.printed_codes(container_ids)

    def _require_reason(self, container_ids, reason: str | None) -> None:
        repetidas = self.reprint_codes(container_ids)
        if repetidas and not (reason or "").strip():
            raise ValueError(
                "Ya se imprimió la etiqueta de " + ", ".join(repetidas[:5])
                + ("…" if len(repetidas) > 5 else "") + ": captura el motivo de la reimpresión.")

    def export_pdf(self, *, actor_user_id: str, container_ids, fmt: ContainerLabelFormat,
                   copies: int = 1, reprint_reason: str | None = None) -> bytes:
        fmt = ContainerLabelFormat(fmt)
        if not fmt.is_pdf:
            raise ValueError("Elige un formato de etiqueta o de hoja para el PDF")
        self._require_reason(container_ids, reprint_reason)
        contenido = self.contents(container_ids)
        datos = self._renderer.pdf(contenido, fmt, copies=copies)   # primero el archivo
        for item in contenido:
            self._logistics.create_label_and_print(
                actor_user_id=actor_user_id, container_id=item.container_id,
                printer_id=f"PDF:{fmt.value}", operation_id=new_uuid(), copies=copies,
                reprint_reason=(reprint_reason or "").strip() or None, printer=_RecordOnly())
        return datos

    def print_thermal(self, *, actor_user_id: str, container_ids, copies: int = 1,
                      reprint_reason: str | None = None) -> int:
        self._require_reason(container_ids, reprint_reason)
        contenido = self.contents(container_ids)
        for item in contenido:
            job = self._logistics.create_label_and_print(
                actor_user_id=actor_user_id, container_id=item.container_id,
                printer_id="routed", operation_id=new_uuid(), copies=copies,
                reprint_reason=(reprint_reason or "").strip() or None)
            if job is not None and job.status == "ERROR":
                raise ValueError(job.error or "No se pudo imprimir la etiqueta")
        return len(contenido)
