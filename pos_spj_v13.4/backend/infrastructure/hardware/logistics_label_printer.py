"""Etiqueta del contenedor (QR permanente) por la impresora que Document Output
asigna a `CONTAINER_LABEL` (integración Logística 32cfbf).

Implementa el `PrinterGateway` de Logística: recibe el trabajo y el token del QR
y entrega ESC/POS (código legible + QR). Sin impresora asignada falla con un
motivo para el operador; el servicio deja el trabajo en ERROR con ese motivo.
"""

from __future__ import annotations

from backend.domain.document_output.enums import DocumentType
from backend.domain.logistics.labels import ContainerLabelContent
from backend.infrastructure.printing.container_label_renderer import render_escpos
from backend.infrastructure.printing.routed_printer import (
    paper_width_mm,
    resolve_routed_device,
    send,
)

NO_CONTAINER_PRINTER_MESSAGE = (
    "No hay impresora asignada a la etiqueta de contenedor en esta sucursal. Asígnala "
    "en Configuración → Dispositivos (ruta de impresión «Etiqueta de contenedor»), o "
    "genera el PDF y imprímelo en cualquier impresora.")


class LogisticsContainerLabelPrinter:
    def __init__(self, connection, *, branch_id: str | None = None,
                 workstation_id: str | None = None) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._workstation_id = workstation_id

    def _content(self, label_id: str, payload: str) -> ContainerLabelContent:
        fila = self._conn.execute(
            "SELECT c.id, c.container_code, t.name, t.category, c.tare_weight,"
            " c.capacity_weight, c.qr_version FROM logistics_container_labels l"
            " JOIN logistics_physical_containers c ON c.id = l.container_id"
            " JOIN logistics_container_types t ON t.id = c.container_type_id"
            " WHERE l.id=?", (label_id,)).fetchone()
        if fila is None:
            return ContainerLabelContent("", "", "", "", "0", None, "", payload, 1)
        return ContainerLabelContent(str(fila[0]), str(fila[1]), str(fila[2] or ""),
                                     str(fila[3] or ""), str(fila[4] or "0"),
                                     str(fila[5]) if fila[5] else None, "", payload,
                                     int(fila[6] or 1))

    def render(self, *, content: ContainerLabelContent, paper_mm: int,
               copies: int = 1) -> bytes:
        return render_escpos(content, paper_mm=paper_mm, copies=copies)

    def submit(self, job, payload: str) -> None:
        device, profile = resolve_routed_device(
            self._conn, DocumentType.CONTAINER_LABEL.value, branch_id=self._branch_id,
            workstation_id=self._workstation_id, module="logistics",
            no_printer_message=NO_CONTAINER_PRINTER_MESSAGE)
        datos = self.render(content=self._content(job.label_id, payload),
                            paper_mm=paper_width_mm(profile), copies=job.copies)
        send(device, profile, datos, what="la etiqueta del contenedor")
