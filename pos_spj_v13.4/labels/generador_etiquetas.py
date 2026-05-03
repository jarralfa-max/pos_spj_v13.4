
# labels/generador_etiquetas.py — SPJ POS v11
"""
Generador de etiquetas QR para impresoras térmicas.
Formatos: 50x30mm, 60x40mm, 80x50mm
Tipos: contenedor_proveedor, producto, fidelidad, ticket_delivery
"""
from __future__ import annotations
import io, logging
from datetime import datetime
from typing import Literal

logger = logging.getLogger("spj.labels")

TAMANOS = {
    "50x30":  (189, 113),   # px a 96dpi
    "60x40":  (227, 151),
    "80x50":  (302, 189),
}

TamanoLabel = Literal["50x30", "60x40", "80x50"]


class GeneradorEtiquetas:
    """
    Genera etiquetas en formato PNG/PDF para impresoras térmicas.
    Si PIL/reportlab no están instalados, genera HTML imprimible.
    """

    def __init__(self, tamano: TamanoLabel = "60x40", conn=None):
        self.tamano = tamano
        self.ancho_px, self.alto_px = TAMANOS.get(tamano, (227, 151))
        self.conn = conn
        self._has_pil = self._check_pil()
        self._has_reportlab = self._check_reportlab()

    @staticmethod
    def _check_pil() -> bool:
        try: from PIL import Image, ImageDraw, ImageFont; return True
        except ImportError: return False

    @staticmethod
    def _check_reportlab() -> bool:
        try: import reportlab; return True
        except ImportError: return False

    # ── Etiqueta contenedor proveedor ─────────────────────────────
    def etiqueta_contenedor(self, datos: dict) -> bytes:
        """
        datos: uuid_qr, proveedor, producto, numero_lote,
               fecha_recepcion, peso_kg, sucursal
        """
        contenido_qr = f"SPJ:CONT:{datos['uuid_qr']}"
        return self._generar(
            uuid_qr=datos["uuid_qr"],
            contenido_qr=contenido_qr,
            lineas=[
                ("titulo",  "CONTENEDOR PROVEEDOR"),
                ("bold",    datos.get("producto", "Sin nombre")),
                ("normal",  f"Prov: {datos.get('proveedor','—')}"),
                ("normal",  f"Lote: {datos.get('numero_lote','—')}"),
                ("small",   f"Recep: {datos.get('fecha_recepcion', datetime.now().strftime('%d/%m/%Y'))}"),
                ("small",   f"Peso: {datos.get('peso_kg','—')} kg"),
                ("small",   f"Suc: {datos.get('sucursal','Principal')}"),
            ]
        )

    # ── Etiqueta producto ──────────────────────────────────────────
    def etiqueta_producto(self, datos: dict) -> bytes:
        """
        datos: uuid_qr, nombre, codigo, precio, lote, sucursal
        """
        contenido_qr = f"SPJ:PROD:{datos['uuid_qr']}"
        return self._generar(
            uuid_qr=datos["uuid_qr"],
            contenido_qr=contenido_qr,
            lineas=[
                ("bold",   datos.get("nombre", "Producto")),
                ("normal", f"Cód: {datos.get('codigo','—')}"),
                ("normal", f"${float(datos.get('precio',0)):.2f}/kg"),
                ("small",  f"Lote: {datos.get('lote','—')}"),
                ("small",  f"{datos.get('sucursal','Principal')}"),
            ]
        )

    # ── Etiqueta fidelidad cliente ─────────────────────────────────
    def etiqueta_fidelidad(self, datos: dict) -> bytes:
        """
        datos: uuid_qr, nombre_cliente, puntos, telefono
        """
        contenido_qr = f"SPJ:FIDEL:{datos['uuid_qr']}"
        return self._generar(
            uuid_qr=datos["uuid_qr"],
            contenido_qr=contenido_qr,
            lineas=[
                ("titulo", "TARJETA FIDELIDAD"),
                ("bold",   datos.get("nombre_cliente", "Cliente")),
                ("normal", f"Tel: {datos.get('telefono','—')}"),
                ("normal", f"Puntos: {datos.get('puntos', 0)}"),
                ("small",  "Escanea para acumular puntos"),
            ]
        )

    # ── Etiqueta ticket delivery ───────────────────────────────────
    def etiqueta_delivery(self, datos: dict) -> bytes:
        """
        datos: uuid_qr, folio, cliente, direccion, total, repartidor
        """
        contenido_qr = f"SPJ:DEL:{datos['uuid_qr']}"
        return self._generar(
            uuid_qr=datos["uuid_qr"],
            contenido_qr=contenido_qr,
            lineas=[
                ("titulo", f"DELIVERY #{datos.get('folio','—')}"),
                ("bold",   datos.get("cliente", "Cliente")),
                ("normal", datos.get("direccion", "Sin dirección")[:30]),
                ("normal", f"Total: ${float(datos.get('total',0)):.2f}"),
                ("small",  f"Repartidor: {datos.get('repartidor','—')}"),
            ]
        )

    # ── Motor de renderizado ───────────────────────────────────────
    def _generar(self, uuid_qr: str, contenido_qr: str, lineas: list) -> bytes:
        if self._has_pil:
            return self._render_pil(uuid_qr, contenido_qr, lineas)
        return self._render_html(uuid_qr, contenido_qr, lineas).encode()

    def _render_pil(self, uuid_qr: str, contenido_qr: str, lineas: list) -> bytes:
        from PIL import Image, ImageDraw, ImageFont
        from services.qr_service import QRService
        import io

        W, H = self.ancho_px, self.alto_px
        img  = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(img)

        # QR en lado izquierdo
        try:
            qr_svc   = QRService(self.conn)
            qr_bytes = qr_svc.generar_imagen_qr(contenido_qr, size=min(W//2, H-4))
            qr_img   = Image.open(io.BytesIO(qr_bytes)).resize((H-8, H-8))
            img.paste(qr_img, (4, 4))
        except Exception as e:
            logger.debug("QR image error: %s", e)
            draw.rectangle([4, 4, H-4, H-4], outline="black", width=2)
            draw.text((10, H//2), uuid_qr[:12], fill="black")

        # Texto en lado derecho
        x_text = H + 6
        y = 4
        for estilo, texto in lineas:
            size = {"titulo": 10, "bold": 11, "normal": 9, "small": 7}.get(estilo, 9)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
            except Exception:
                font = ImageFont.load_default()
            draw.text((x_text, y), texto, fill="black", font=font)
            y += size + 3
            if y > H - size: break

        buf = io.BytesIO()
        img.save(buf, format="PNG", dpi=(203, 203))
        return buf.getvalue()

    def _render_html(self, uuid_qr: str, contenido_qr: str, lineas: list) -> str:
        """Genera HTML imprimible cuando PIL no está disponible."""
        try:
            from services.qr_service import QRService
            qr_b64 = QRService(self.conn).generar_imagen_qr_b64(contenido_qr)
        except Exception:
            qr_b64 = ""
        ancho_mm, alto_mm = self.tamano.split("x")
        lineas_html = ""
        for estilo, texto in lineas:
            fs = {"titulo":"10px","bold":"11px","normal":"9px","small":"7px"}.get(estilo,"9px")
            fw = "bold" if estilo in ("titulo","bold") else "normal"
            lineas_html += f'<div style="font-size:{fs};font-weight:{fw};overflow:hidden;white-space:nowrap;">{texto}</div>'
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  @media print {{
    @page {{ size: {ancho_mm}mm {alto_mm}mm; margin: 0; }}
    body {{ margin: 0; }}
  }}
  body {{ font-family: Arial, sans-serif; }}
  .etiqueta {{
    width:{ancho_mm}mm; height:{alto_mm}mm; overflow:hidden;
    display:flex; align-items:flex-start; padding:2mm; box-sizing:border-box;
    border: 0.5px solid #ccc;
  }}
  .qr {{ flex-shrink:0; width:{int(alto_mm)-4}mm; height:{int(alto_mm)-4}mm; margin-right:3mm; }}
  .qr img {{ width:100%; height:100%; }}
  .texto {{ flex:1; overflow:hidden; }}
</style></head><body>
<div class="etiqueta">
  <div class="qr">{"<img src='"+qr_b64+"'>" if qr_b64 else f"<div style='border:2px solid black;width:100%;height:100%;'>{uuid_qr[:8]}</div>"}</div>
  <div class="texto">{lineas_html}</div>
</div>
</body></html>"""

    def generar_lote(self, items: list, tipo: str) -> list:
        """Genera múltiples etiquetas. items: lista de dicts con datos."""
        metodos = {
            "contenedor":     self.etiqueta_contenedor,
            "producto":       self.etiqueta_producto,
            "fidelidad":      self.etiqueta_fidelidad,
            "delivery":       self.etiqueta_delivery,
        }
        fn = metodos.get(tipo)
        if not fn:
            raise ValueError(f"Tipo de etiqueta desconocido: {tipo}")
        return [fn(item) for item in items]
