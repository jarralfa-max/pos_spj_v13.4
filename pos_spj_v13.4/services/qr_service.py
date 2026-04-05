
# services/qr_service.py — SPJ POS v11
"""
Servicio central de QR.
Genera, valida y registra QR para:
  - Contenedores de proveedor
  - Productos individuales
  - Tarjetas de fidelidad de clientes
  - Tickets de delivery
  - Mapa de entrega
"""
from __future__ import annotations
import uuid, json, logging, io, base64
from datetime import datetime
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.qr")

TIPOS_QR = ("contenedor", "producto", "cliente_fidelidad", "ticket_delivery", "mapa_entrega", "paquete")


class QRService:
    def __init__(self, conn=None, sucursal_id: int = 1):
        self.conn        = conn or get_connection()
        self.sucursal_id = sucursal_id

    # ── Generacion ──────────────────────────────────────────────────
    def generar_uuid_qr(self, tipo: str, datos: dict) -> str:
        """Genera un UUID único y lo registra en trazabilidad_qr."""
        if tipo not in TIPOS_QR:
            raise ValueError(f"Tipo QR inválido: {tipo}")
        uid = str(uuid.uuid4()).replace("-", "").upper()[:20]
        uid = f"{tipo[:3].upper()}{uid}"
        with transaction(self.conn) as c:
            c.execute("""INSERT INTO trazabilidad_qr
                (uuid_qr, tipo, producto_id, proveedor_id, lote_id,
                 sucursal_id, numero_lote, peso_kg, cantidad, datos_extra)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (uid, tipo,
                 datos.get("producto_id"),
                 datos.get("proveedor_id"),
                 datos.get("lote_id"),
                 datos.get("sucursal_id", self.sucursal_id),
                 datos.get("numero_lote"),
                 datos.get("peso_kg"),
                 datos.get("cantidad"),
                 json.dumps(datos, default=str)))
            c.execute("""INSERT INTO movimientos_trazabilidad
                (uuid_qr, evento, origen, sucursal_id, usuario, notas)
                VALUES(?,'generado','sistema',?,?,?)""",
                (uid, self.sucursal_id,
                 datos.get("usuario", "sistema"),
                 f"QR {tipo} generado"))
        logger.info("QR generado: %s tipo=%s", uid, tipo)
        return uid

    def generar_imagen_qr(self, contenido: str,
                          size: int = 300, border: int = 4) -> bytes:
        """
        Genera la imagen PNG del QR.
        Usa qrcode si disponible; fallback: SVG básico.
        """
        try:
            import qrcode
            from PIL import Image
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10, border=border)
            qr.add_data(contenido)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            return self._qr_svg_fallback(contenido, size)

    def generar_imagen_qr_b64(self, contenido: str) -> str:
        """Retorna imagen QR como base64 para embeber en HTML."""
        png = self.generar_imagen_qr(contenido)
        return "data:image/png;base64," + base64.b64encode(png).decode()

    def _qr_svg_fallback(self, texto: str, size: int) -> bytes:
        """SVG placeholder cuando qrcode no está instalado."""
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
               f'<rect width="{size}" height="{size}" fill="white"/>'
               f'<rect x="10" y="10" width="80" height="80" fill="none" stroke="black" stroke-width="8"/>'
               f'<rect x="30" y="30" width="40" height="40" fill="black"/>'
               f'<text x="{size//2}" y="{size-20}" text-anchor="middle" font-size="12">{texto[:20]}</text>'
               f'</svg>')
        return svg.encode()

    # ── Escaneo / Recepcion ──────────────────────────────────────────
    def escanear_recepcion(self, uuid_qr: str, peso_kg: float = None,
                           usuario: str = "almacen") -> dict:
        """Registra la recepcion de un contenedor (llegada de proveedor)."""
        row = self.conn.execute(
            "SELECT * FROM trazabilidad_qr WHERE uuid_qr=?", (uuid_qr,)).fetchone()
        if not row:
            return {"ok": False, "error": f"QR {uuid_qr} no encontrado"}
        row = dict(row)
        with transaction(self.conn) as c:
            c.execute("""UPDATE trazabilidad_qr
                SET estado='recibido', fecha_recepcion=datetime('now'),
                    peso_kg=COALESCE(?,peso_kg)
                WHERE uuid_qr=?""", (peso_kg, uuid_qr))
            c.execute("""INSERT INTO movimientos_trazabilidad
                (uuid_qr, evento, origen, destino, sucursal_id, usuario, notas)
                VALUES(?,'recibido','proveedor','almacen',?,?,?)""",
                (uuid_qr, self.sucursal_id, usuario,
                 f"Recepción — peso: {peso_kg}kg" if peso_kg else "Recepción"))
            # Actualizar inventario si hay producto y peso
            if row.get("producto_id") and peso_kg:
                c.execute(
                    "UPDATE productos SET existencia=existencia+? WHERE id=?",
                    (peso_kg, row["producto_id"]))
        return {"ok": True, "uuid_qr": uuid_qr, "datos": row}

    def escanear_venta(self, uuid_qr: str, venta_id: int,
                       cliente_id: int = None, usuario: str = "cajero") -> bool:
        """Vincula un QR a una venta — completa la trazabilidad."""
        with transaction(self.conn) as c:
            c.execute("""UPDATE trazabilidad_qr
                SET estado='vendido', fecha_venta=datetime('now'),
                    venta_id=?, cliente_id=?
                WHERE uuid_qr=?""", (venta_id, cliente_id, uuid_qr))
            c.execute("""INSERT INTO movimientos_trazabilidad
                (uuid_qr, evento, origen, destino, sucursal_id, usuario, notas)
                VALUES(?,'vendido','almacen','cliente',?,?,?)""",
                (uuid_qr, self.sucursal_id, usuario, f"Venta #{venta_id}"))
        return True

    # ── Consulta trazabilidad ───────────────────────────────────────
    def get_trazabilidad(self, uuid_qr: str) -> dict:
        """Historial completo de un QR: proveedor → recepción → venta."""
        qr = self.conn.execute(
            "SELECT * FROM trazabilidad_qr WHERE uuid_qr=?", (uuid_qr,)).fetchone()
        if not qr:
            return {"ok": False, "error": "QR no encontrado"}
        movs = self.conn.execute(
            "SELECT * FROM movimientos_trazabilidad WHERE uuid_qr=? ORDER BY fecha",
            (uuid_qr,)).fetchall()
        return {
            "ok":        True,
            "qr":        dict(qr),
            "historial": [dict(m) for m in movs],
        }

    def get_qr_info(self, uuid_qr: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM trazabilidad_qr WHERE uuid_qr=?", (uuid_qr,)).fetchone()
        return dict(row) if row else None

    # ── QR de fidelidad para cliente ────────────────────────────────
    def qr_fidelidad_cliente(self, cliente_id: int) -> str:
        """Retorna (o crea) el QR de fidelidad del cliente. Idempotente."""
        row = self.conn.execute(
            """SELECT uuid_qr FROM trazabilidad_qr
               WHERE tipo='cliente_fidelidad' AND datos_extra LIKE ?
               ORDER BY id LIMIT 1""",
            (f'%"cliente_id": {cliente_id}%',)).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT uuid_qr FROM trazabilidad_qr WHERE tipo='cliente_fidelidad' AND cliente_id=?",
                (cliente_id,)).fetchone()
        if row:
            return row[0]
        uid = self.generar_uuid_qr("cliente_fidelidad", {"cliente_id": cliente_id})
        # Guardar cliente_id en columna para búsqueda rápida
        self.conn.execute(
            "UPDATE trazabilidad_qr SET cliente_id=? WHERE uuid_qr=?",
            (cliente_id, uid))
        try: self.conn.commit()
        except Exception: pass
        return uid

    # ── QR de contenedor proveedor ──────────────────────────────────
    def qr_contenedor_proveedor(self, proveedor_id: int, producto_id: int,
                                 numero_lote: str, peso_kg: float,
                                 usuario: str = "almacen") -> str:
        return self.generar_uuid_qr("contenedor", {
            "proveedor_id": proveedor_id,
            "producto_id":  producto_id,
            "numero_lote":  numero_lote,
            "peso_kg":      peso_kg,
            "usuario":      usuario,
        })
