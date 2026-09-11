"""Plantilla HTML del ticket de venta.

Reemplaza `core/engines/template_engine.py`, borrado. El formato de los
marcadores no se inventó: es `{{campo}}`, visible en la plantilla que sembraba
`tests/test_sales_service_single_event_flow.py` (`"<html>{{folio}}</html>"`), y
los campos que la plantilla por omisión debe traer los enumera
`tests/integration/test_sale_ticket_default_template.py`.

QUÉ RENDERIZA, Y QUÉ NO
-----------------------
Sustitución de `{{campo}}` sobre un diccionario aplanado, más un bloque
`{{items}}` que se expande a las líneas de la venta. No hay condicionales ni
bucles generales: si la plantilla que un usuario guardó en el diseñador usaba
una sintaxis de bucle propia, sus renglones NO se expandirán — saldrá el
marcador tal cual en vez de los productos.

Se prefiere que eso se vea a adivinar una sintaxis que no puedo comprobar. La
plantilla por omisión, que es la que usa la inmensa mayoría de instalaciones,
sí funciona entera.

UN MARCADOR SIN DATO SE QUEDA VACÍO, no se deja escrito. Un ticket que dice
"Total: {{total}}" es peor que uno que dice "Total:": el segundo se ve roto de
inmediato, el primero parece un dato literal.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

#: Marcador que se expande a los renglones de la venta.
ITEMS_PLACEHOLDER = "items"


def _money(value: Any) -> str:
    """`$100.00`. Un valor ilegible se muestra como `$0.00`.

    Dejar el texto crudo en un importe sería peor: un ticket con "Total: abc"
    parece un precio, y nadie revisa un ticket impreso contra la base.
    """
    try:
        amount = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    return f"${amount:,.2f}"


def default_ticket_template() -> str:
    """Plantilla usada cuando la instalación no tiene una configurada.

    Su ausencia NUNCA puede bloquear una venta: el cobro ya ocurrió, y no
    poder imprimir el comprobante no deshace nada.
    """
    return """<html>
<head><meta charset="utf-8"><style>
body { font-family: monospace; width: 280px; margin: 0; }
.centro { text-align: center; }
.linea { border-top: 1px dashed #000; margin: 4px 0; }
table { width: 100%; border-collapse: collapse; }
td.num { text-align: right; }
</style></head>
<body>
  <div class="centro">
    <strong>{{nombre_empresa}}</strong><br>
    {{sucursal_nombre}}<br>
    {{sucursal_direccion}}<br>
    {{sucursal_telefono}}
  </div>
  <div class="linea"></div>
  <div>Folio: {{folio}}</div>
  <div>Fecha: {{fecha}}</div>
  <div>Atendió: {{cajero}}</div>
  <div class="linea"></div>
  <table>{{items}}</table>
  <div class="linea"></div>
  <table>
    <tr><td>Subtotal</td><td class="num">{{subtotal}}</td></tr>
    <tr><td>Descuento</td><td class="num">{{descuento}}</td></tr>
    <tr><td><strong>Total</strong></td><td class="num"><strong>{{total}}</strong></td></tr>
  </table>
  <div>Forma de pago: {{forma_pago}}</div>
  <div class="linea"></div>
  <div class="centro">{{mensaje_psicologico}}</div>
</body>
</html>"""


class TicketTemplateEngine:
    def __init__(self, db_conn=None) -> None:
        # La conexión se acepta por compatibilidad con los llamadores actuales.
        # Este motor no la usa: todo lo que imprime llega en `datos`, y leer de
        # la base al renderizar haría que el mismo ticket saliera distinto
        # según cuándo se reimprimiera.
        self._db = db_conn

    def generar_ticket(
        self, template_html: str, datos: dict, mensaje_psicologico: str = "",
    ) -> str:
        campos = self._flatten(datos or {}, mensaje_psicologico)
        return _PLACEHOLDER.sub(lambda m: campos.get(m.group(1), ""), template_html or "")

    def _flatten(self, datos: dict, mensaje_psicologico: str) -> dict[str, str]:
        totales = datos.get("totales") or {}
        campos: dict[str, str] = {
            clave: html.escape(str(valor))
            for clave, valor in datos.items()
            if not isinstance(valor, (dict, list))
        }
        campos.update({
            "subtotal": _money(totales.get("subtotal")),
            "descuento": _money(totales.get("descuento")),
            # `total` viene de `total_final`: es el importe que se cobró, no el
            # de antes del descuento.
            "total": _money(totales.get("total_final", totales.get("total"))),
            "mensaje_psicologico": html.escape(str(mensaje_psicologico or "")),
            ITEMS_PLACEHOLDER: self._render_items(datos.get("items") or []),
        })
        return campos

    @staticmethod
    def _render_items(items: list) -> str:
        """Un renglón por producto.

        Los textos se escapan: el nombre de un producto puede llevar `&` o `<`
        y romper el HTML del ticket entero.
        """
        filas = []
        for item in items:
            if not isinstance(item, dict):
                continue
            nombre = html.escape(str(item.get("nombre") or ""))
            cantidad = item.get("cantidad", "")
            filas.append(
                f'<tr><td>{cantidad} x {nombre}</td>'
                f'<td class="num">{_money(item.get("total"))}</td></tr>'
            )
        return "".join(filas)
