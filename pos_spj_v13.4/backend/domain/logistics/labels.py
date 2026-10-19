"""Etiqueta del contenedor: qué lleva y en qué formatos sale (2026-10-17).

Valores puros; el dibujo (PDF, vista previa, ESC/POS) vive en infraestructura.
El QR lleva sólo la identidad permanente (`qr_identity`); lo legible es el
código en grande para captura manual, el tipo, la tara y la empresa dueña.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class ContainerLabelContent:
    container_id: str
    code: str
    type_name: str
    category_label: str
    tare_weight: str
    capacity_weight: str | None
    owner_name: str
    qr_payload: str
    qr_version: int


class ContainerLabelFormat(str, Enum):
    """Medidas en mm: ancho × alto de una etiqueta; las hojas acomodan varias."""

    LABEL_100X50 = "LABEL_100X50"
    LABEL_50X30 = "LABEL_50X30"
    SHEET_LETTER_2X5 = "SHEET_LETTER_2X5"
    THERMAL_ROLL = "THERMAL_ROLL"

    @property
    def label(self) -> str:
        return {
            "LABEL_100X50": "Etiqueta 100 × 50 mm (impresora de etiquetas)",
            "LABEL_50X30": "Etiqueta 50 × 30 mm (impresora de etiquetas)",
            "SHEET_LETTER_2X5": "Hoja carta, 10 etiquetas de 101 × 51 mm",
            "THERMAL_ROLL": "Impresora térmica de tickets (ruta «Etiqueta de contenedor»)",
        }[self.value]

    @property
    def is_pdf(self) -> bool:
        return self is not ContainerLabelFormat.THERMAL_ROLL
