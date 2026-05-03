# core/engines/template_engine.py — SPJ POS v13
import re
import logging

logger = logging.getLogger(__name__)


class TemplateEngine:
    """Motor base de renderizado para Tickets y Etiquetas."""

    def render(self, template_str: str, data: dict) -> str:
        def replace_match(match):
            key = match.group(1).strip()
            return str(data.get(key, ""))
        pattern = re.compile(r"\{\{(.*?)\}\}")
        return pattern.sub(replace_match, template_str)


class TicketTemplateEngine(TemplateEngine):
    """Especializado en tickets de venta con datos fiscales completos."""

    def __init__(self, db_conn=None):
        self._db = db_conn
        self._config_cache: dict = {}

    def _get_config(self, clave: str, default: str = "") -> str:
        if clave in self._config_cache:
            return self._config_cache[clave]
        try:
            if self._db:
                row = self._db.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
                ).fetchone()
                val = row[0] if row and row[0] else default
                self._config_cache[clave] = val
                return val
        except Exception:
            pass
        return default

    def generar_ticket(self, template_db: str, venta_data: dict,
                       mensaje_psicologico: str = "") -> str:
        totales  = venta_data.get("totales", {})
        total    = float(totales.get("total_final", 0))
        subtotal = float(totales.get("subtotal", total))
        desc     = float(totales.get("descuento", 0))

        try:
            tasa_iva = float(self._get_config("tasa_iva", "0"))
        except Exception:
            tasa_iva = 0.0

        if tasa_iva > 0:
            base_iva  = round(total / (1 + tasa_iva), 4)
            monto_iva = round(total - base_iva, 4)
        else:
            base_iva = total; monto_iva = 0.0

        fp_map = {
            "efectivo": "01 - Efectivo",
            "tarjeta":  "04 - Tarjeta de crédito/débito",
            "transferencia": "03 - Transferencia electrónica",
            "credito":  "99 - Por definir",
        }
        fp_raw     = str(venta_data.get("forma_pago", "efectivo")).lower()
        forma_pago = fp_map.get(fp_raw, venta_data.get("forma_pago", "Efectivo"))

        ctx = {
            "folio":             str(venta_data.get("venta_id", "")),
            "folio_fiscal":      venta_data.get("uuid_cfdi", ""),
            "fecha":             venta_data.get("fecha", ""),
            "turno":             venta_data.get("turno", ""),
            "cajero":            venta_data.get("cajero", ""),
            "nombre_empresa":    self._get_config("nombre_empresa", "SPJ"),
            "rfc_emisor":        self._get_config("rfc", ""),
            "regimen_fiscal":    self._get_config("regimen_fiscal", ""),
            "direccion":         self._get_config("direccion", ""),
            "telefono_empresa":  self._get_config("telefono_empresa", ""),
            "web_empresa":       self._get_config("web_empresa", ""),
            "cliente_nombre":    venta_data.get("cliente", "Público General"),
            "cliente_rfc":       venta_data.get("cliente_rfc", ""),
            "subtotal":          f"${subtotal:,.2f}",
            "descuento":         f"${desc:,.2f}" if desc > 0 else "",
            "base_iva":          f"${base_iva:,.2f}" if monto_iva > 0 else "",
            "iva":               f"${monto_iva:,.2f}" if monto_iva > 0 else "",
            "tasa_iva":          f"{tasa_iva*100:.0f}%" if tasa_iva > 0 else "0%",
            "total":             f"${total:,.2f}",
            "efectivo":          f"${float(venta_data.get('efectivo_recibido', 0)):,.2f}",
            "cambio":            f"${float(venta_data.get('cambio', 0)):,.2f}",
            "forma_pago":        forma_pago,
            "puntos_ganados":    str(venta_data.get("puntos_ganados", "")),
            "puntos_totales":    str(venta_data.get("puntos_totales", "")),
            "items_html":        self._generar_filas_items(venta_data.get("items", [])),
            "items_texto":       self._generar_items_texto(venta_data.get("items", [])),
            "mensaje_psicologico": mensaje_psicologico,
        }
        return self.render(template_db, ctx)

    def _generar_filas_items(self, items: list) -> str:
        filas = ""
        for item in items:
            nombre = item.get("nombre", "")
            cant   = item.get("cantidad", "")
            precio = float(item.get("precio_unitario", item.get("precio", 0)))
            total  = float(item.get("total", item.get("subtotal", 0)))
            filas += (
                "<tr>"
                f"<td>{nombre}</td>"
                f"<td style=\'text-align:right\'>{cant}</td>"
                f"<td style=\'text-align:right\'>${precio:.2f}</td>"
                f"<td style=\'text-align:right\'>${total:.2f}</td>"
                "</tr>"
            )
        return filas

    def _generar_items_texto(self, items: list) -> str:
        lineas = []
        for item in items:
            nombre = item.get("nombre", "")[:24]
            cant   = str(item.get("cantidad", ""))
            total  = float(item.get("total", item.get("subtotal", 0)))
            lineas.append(f"{nombre:<24} {cant:>6} ${total:>8.2f}")
        return "\n".join(lineas)


class LabelTemplateEngine(TemplateEngine):
    """Especializado en etiquetas Zebra/ZPL."""

    def generar_etiqueta_zpl(self, template_zpl: str, producto_data: dict) -> str:
        return self.render(template_zpl, producto_data)
