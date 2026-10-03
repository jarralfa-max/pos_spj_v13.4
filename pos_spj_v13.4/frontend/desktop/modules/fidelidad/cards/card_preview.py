"""Vista previa de una cara de tarjeta (LOY-29).

Dibuja el diseño declarativo a escala con los colores del tema, el área segura
y las capas en orden, con valores de ejemplo. El QR y el código de barras son
marcadores: los reales los genera el renderizador con el token de cada tarjeta.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QPainter, QPalette, QPen
from PyQt5.QtWidgets import QWidget

#: CR80, la tarjeta estándar (§38).
DEFAULT_CANVAS = {"width_mm": "85.6", "height_mm": "53.98"}
SAFE_AREA_MM = Decimal("3")

#: Valores de ejemplo de la vista previa; los reales llegan por tarjeta.
SAMPLE_VALUES = {
    "customer_name": "Ana Torres", "card_number": "LC-00000001", "membership_tier": "Oro",
    "points_balance": "", "expiry_date": "2027-12-31", "program_name": "Puntos SPJ",
}


def _texto_muestra(contenido: str) -> str:
    resultado = contenido
    for clave, valor in SAMPLE_VALUES.items():
        resultado = resultado.replace("{{" + clave + "}}", valor or "")
    return resultado


class CardPreview(QWidget):
    """Dibuja una cara de la tarjeta a escala con los colores del tema."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fidelidadCardPreview")
        self.setAccessibleName("Vista previa de la tarjeta")
        self.setMinimumSize(320, 210)
        self._canvas = dict(DEFAULT_CANVAS)
        self._elements: list[dict] = []
        self._selected: int | None = None

    def show_design(self, canvas: dict, elements: list[dict], selected: int | None) -> None:
        self._canvas, self._elements, self._selected = canvas, elements, selected
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt override
        ancho_mm = float(Decimal(str(self._canvas["width_mm"])))
        alto_mm = float(Decimal(str(self._canvas["height_mm"])))
        escala = min((self.width() - 20) / ancho_mm, (self.height() - 20) / alto_mm)
        x0 = (self.width() - ancho_mm * escala) / 2
        y0 = (self.height() - alto_mm * escala) / 2
        pal = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(QRectF(x0, y0, ancho_mm * escala, alto_mm * escala), pal.color(QPalette.Base))
        p.setPen(QPen(pal.color(QPalette.Mid), 1))
        p.drawRect(QRectF(x0, y0, ancho_mm * escala, alto_mm * escala))
        seguro = float(SAFE_AREA_MM) * escala
        p.setPen(QPen(pal.color(QPalette.Mid), 1, Qt.DashLine))
        p.drawRect(QRectF(x0 + seguro, y0 + seguro, ancho_mm * escala - 2 * seguro,
                          alto_mm * escala - 2 * seguro))
        for indice, el in enumerate(self._elements):
            try:
                r = QRectF(x0 + float(Decimal(str(el["x_mm"]))) * escala,
                           y0 + float(Decimal(str(el["y_mm"]))) * escala,
                           float(Decimal(str(el["width_mm"]))) * escala,
                           max(float(Decimal(str(el["height_mm"]))) * escala, 1.0))
            except (InvalidOperation, KeyError, ValueError):
                continue
            color = pal.color(QPalette.Highlight) if indice == self._selected else pal.color(
                QPalette.Text)
            p.setPen(QPen(color, 1))
            tipo = el.get("type")
            if tipo == "TEXT":
                fuente = p.font()
                fuente.setPixelSize(max(int(r.height() * 0.7), 6))
                p.setFont(fuente)
                alineacion = {"CENTER": Qt.AlignHCenter, "RIGHT": Qt.AlignRight}.get(
                    el.get("align", "LEFT"), Qt.AlignLeft)
                p.drawText(r, alineacion | Qt.AlignVCenter, _texto_muestra(el.get("content", "")))
            elif tipo == "QR":
                p.drawRect(r)
                paso = r.width() / 5
                for i in range(5):
                    for j in range(5):
                        if (i * 3 + j) % 2 == 0:
                            p.fillRect(QRectF(r.x() + i * paso, r.y() + j * paso, paso, paso), color)
            elif tipo == "BARCODE":
                barras = max(int(r.width() / 3), 1)
                for i in range(barras):
                    if i % 3 != 1:
                        p.fillRect(QRectF(r.x() + i * 3, r.y(), 1.5, r.height()), color)
            elif tipo == "SHAPE":
                forma = el.get("shape_type")
                if forma == "CIRCLE":
                    p.drawEllipse(r)
                elif forma == "LINE":
                    p.drawLine(r.topLeft(), r.bottomRight())
                else:
                    p.drawRect(r)
            elif tipo == "IMAGE":
                p.drawRect(r)
                p.drawText(r, Qt.AlignCenter, "Logo" if el.get("source") == "LOGO" else "Imagen")
        p.end()


__all__ = ["CardPreview", "DEFAULT_CANVAS", "SAFE_AREA_MM", "SAMPLE_VALUES"]
