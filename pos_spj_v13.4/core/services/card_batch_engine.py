
# core/services/card_batch_engine.py
# ── Motor de Lotes de Tarjetas SPJ v9 ────────────────────────────────────
# Maneja el ciclo completo de tarjetas de fidelidad:
#   generacion_lote → generada → impresa → libre → asignada / bloqueada
# Genera QR individual y exporta PDF de lote para imprenta.
# Registro completo en card_assignment_history.
from __future__ import annotations
from backend.shared.ids import new_uuid

import hashlib
import io
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

logger = logging.getLogger("spj.card_batch")

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

try:
    from reportlab.lib.pagesizes import mm, inch
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import HexColor
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ── DTOs ──────────────────────────────────────────────────────────────────────

# NOTA (FASE 4 / REGLA CERO): las identidades (id de lote/tarjeta/cliente) viajan
# como str (UUIDv7-ready). Las columnas id siguen siendo INTEGER PRIMARY KEY hasta
# la migración 200; la afinidad SQLite hace que un str '5' empate con el entero 5.
@dataclass
class CardBatch:
    id:               str
    uuid:             str
    nombre:           str
    codigo_inicio:    str
    codigo_fin:       str
    cantidad:         int
    cantidad_libres:  int
    cantidad_asignadas: int
    estado:           str
    notas:            Optional[str]
    fecha_generacion: str


@dataclass
class Tarjeta:
    id:               str
    numero:           str
    batch_id:         Optional[str]
    estado:           str
    id_cliente:       Optional[str]
    puntos_actuales:  int
    nivel:            str
    codigo_qr:        Optional[str]
    fecha_creacion:   str


@dataclass
class AsignacionResult:
    tarjeta_id:   str
    cliente_id:   Optional[str]
    accion:       str
    exito:        bool
    mensaje:      str


# ── CardBatchEngine ───────────────────────────────────────────────────────────

class CardBatchEngine:
    """
    Motor de gestión de lotes de tarjetas de fidelidad.

    Flujo estándar:
        eng = CardBatchEngine(conn, usuario="admin")
        batch = eng.crear_lote("Lote Enero 2026", prefijo="J", cantidad=500)
        eng.marcar_impreso(batch.id)
        eng.asignar_tarjeta(tarjeta_id, cliente_id)
        eng.bloquear_tarjeta(tarjeta_id, motivo="Extraviada")
    """

    PREFIJO_DEFAULT = "SPJ"

    def __init__(self, conn: sqlite3.Connection, usuario: str = "sistema") -> None:
        self.conn    = conn
        self.usuario = usuario

    # ── Identidad (REGLA CERO) ─────────────────────────────────────────────────
    @staticmethod
    def _sid(v):
        """Normaliza una identidad a str (UUIDv7-ready) o None."""
        return None if v is None else str(v)

    def _batch_from_row(self, row) -> CardBatch:
        vals = list(row)
        vals[0] = self._sid(vals[0])  # id
        return CardBatch(*vals)

    def _tarjeta_from_row(self, row) -> Tarjeta:
        vals = list(row)
        vals[0] = self._sid(vals[0])  # id
        vals[2] = self._sid(vals[2])  # batch_id
        vals[4] = self._sid(vals[4])  # id_cliente
        return Tarjeta(*vals)

    # ── Lotes ─────────────────────────────────────────────────────────────────

    def crear_lote(
        self,
        nombre:    str,
        prefijo:   str = None,
        cantidad:  int = 100,
        notas:     str = "",
    ) -> CardBatch:
        """
        Genera un nuevo lote de N tarjetas con numeración secuencial.
        Formato: {prefijo}{timestamp_corto}{seq:05d}
        Ej: SPJ260001, SPJ260002 ...
        """
        if cantidad <= 0 or cantidad > 10000:
            raise ValueError(f"Cantidad debe ser 1-10000, recibido: {cantidad}")

        pfx = (prefijo or self.PREFIJO_DEFAULT).upper()[:6]
        ts  = datetime.now().strftime("%y%m")  # 2602 para feb 2026

        # Buscar secuencia disponible
        last_row = self.conn.execute(
            "SELECT codigo_fin FROM card_batches ORDER BY id DESC LIMIT 1"
        ).fetchone()

        start_seq = 1
        if last_row:
            try:
                # Extraer número del último código
                last_code = last_row[0]
                num_part  = last_code.replace(pfx, "").replace(ts, "")
                if num_part.isdigit():
                    start_seq = int(num_part) + 1
            except Exception:
                pass

        cod_inicio = f"{pfx}{ts}{start_seq:05d}"
        cod_fin    = f"{pfx}{ts}{start_seq + cantidad - 1:05d}"
        batch_uuid = new_uuid()

        # UUID-native (REGLA CERO): el id del lote es un UUIDv7 acuñado con
        # new_uuid() e insertado explícitamente — sin lastrowid. Requiere el
        # esquema post-corte (migración 200) donde card_batches.id es TEXT.
        batch_id = new_uuid()
        self.conn.execute(
            """
            INSERT INTO card_batches
                (id, uuid, nombre, codigo_inicio, codigo_fin, cantidad,
                 cantidad_libres, estado, notas, generado_por)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (batch_id, batch_uuid, nombre, cod_inicio, cod_fin, cantidad,
             cantidad, "activo", notas, self.usuario)
        )

        # Generar tarjetas individuales (cada id es un UUIDv7 propio, sin lastrowid)
        for i in range(cantidad):
            numero = f"{pfx}{ts}{start_seq + i:05d}"
            qr_str = self._generar_qr_string(numero)
            self.conn.execute(
                """
                INSERT INTO tarjetas_fidelidad
                    (id, numero, codigo_qr, batch_id, estado, activa,
                     es_pregenerada, puntos_actuales, nivel)
                VALUES (?,?,?,?,'generada',1,1,0,'Bronce')
                ON CONFLICT(numero) DO NOTHING
                """,
                (new_uuid(), numero, qr_str, batch_id)
            )

        self.conn.commit()

        logger.info(
            "crear_lote batch=%d nombre='%s' cantidad=%d inicio=%s fin=%s",
            batch_id, nombre, cantidad, cod_inicio, cod_fin
        )

        return self._load_batch(batch_id)

    def _generar_qr_string(self, numero: str) -> str:
        """Genera código hash SHA-256 corto (16 hex) para QR."""
        return hashlib.sha256(numero.encode()).hexdigest()[:16].upper()

    def _load_batch(self, batch_id: str) -> CardBatch:
        row = self.conn.execute(
            """
            SELECT id, uuid, nombre, codigo_inicio, codigo_fin,
                   cantidad, cantidad_libres, cantidad_asignadas,
                   estado, notas, fecha_creacion
            FROM card_batches WHERE id = ?
            """,
            (str(batch_id),)
        ).fetchone()
        if not row:
            raise ValueError(f"Batch {batch_id} no encontrado")
        return self._batch_from_row(row)

    def listar_lotes(self, estado: str = None) -> List[CardBatch]:
        q = "SELECT id, uuid, nombre, codigo_inicio, codigo_fin, " \
            "cantidad, cantidad_libres, cantidad_asignadas, " \
            "estado, notas, fecha_creacion FROM card_batches"
        params: list = []
        if estado:
            q += " WHERE estado = ?"
            params.append(estado)
        q += " ORDER BY id DESC"
        return [self._batch_from_row(r) for r in self.conn.execute(q, params).fetchall()]

    # ── Estados lote ──────────────────────────────────────────────────────────

    def marcar_impreso(self, batch_id: str) -> int:
        """Marca todas las tarjetas del lote como 'impresa'. Retorna n afectadas."""
        n = self.conn.execute(
            "UPDATE tarjetas_fidelidad SET estado='impresa' "
            "WHERE batch_id = ? AND estado = 'generada'",
            (str(batch_id),)
        ).rowcount
        self.conn.commit()
        logger.info("marcar_impreso batch=%s n=%d", batch_id, n)
        return n

    def liberar_lote(self, batch_id: str) -> int:
        """Marca tarjetas impresas del lote como 'libre' (disponibles para asignar)."""
        n = self.conn.execute(
            "UPDATE tarjetas_fidelidad SET estado='libre' "
            "WHERE batch_id = ? AND estado IN ('generada','impresa')",
            (str(batch_id),)
        ).rowcount
        self.conn.commit()
        logger.info("liberar_lote batch=%s n=%d", batch_id, n)
        return n

    def cerrar_lote(self, batch_id: str) -> None:
        self.conn.execute(
            "UPDATE card_batches SET estado='cerrado', fecha_cierre=datetime('now') "
            "WHERE id = ?", (str(batch_id),)
        )
        self.conn.commit()

    # ── Tarjetas ──────────────────────────────────────────────────────────────

    def _load_tarjeta(self, tarjeta_id: str) -> Tarjeta:
        row = self.conn.execute(
            """
            SELECT id, numero, batch_id, estado, id_cliente,
                   puntos_actuales, COALESCE(nivel,'Bronce'), codigo_qr, fecha_creacion
            FROM tarjetas_fidelidad WHERE id = ?
            """,
            (str(tarjeta_id),)
        ).fetchone()
        if not row:
            raise ValueError(f"Tarjeta {tarjeta_id} no encontrada")
        return self._tarjeta_from_row(row)

    def buscar_tarjeta(self, numero_o_qr: str) -> Optional[Tarjeta]:
        """Busca por número exacto o código QR."""
        row = self.conn.execute(
            """
            SELECT id, numero, batch_id, estado, id_cliente,
                   puntos_actuales, COALESCE(nivel,'Bronce'), codigo_qr, fecha_creacion
            FROM tarjetas_fidelidad
            WHERE numero = ? OR codigo_qr = ?
            LIMIT 1
            """,
            (numero_o_qr, numero_o_qr)
        ).fetchone()
        return self._tarjeta_from_row(row) if row else None

    def tarjetas_libres(self, batch_id: str = None, limit: int = 50) -> List[Tarjeta]:
        q = """
        SELECT id, numero, batch_id, estado, id_cliente,
                   puntos_actuales, COALESCE(nivel,'Bronce'), codigo_qr, fecha_creacion
            FROM tarjetas_fidelidad WHERE estado = 'libre'
        """
        params: list = []
        if batch_id is not None:
            q += " AND batch_id = ?"
            params.append(str(batch_id))
        q += f" ORDER BY id LIMIT {limit}"
        return [self._tarjeta_from_row(r) for r in self.conn.execute(q, params).fetchall()]

    # ── Asignación ────────────────────────────────────────────────────────────

    def asignar_tarjeta(
        self,
        tarjeta_id: str,
        cliente_id: str,
        motivo:     str = "asignacion_normal",
    ) -> AsignacionResult:
        """Asigna tarjeta libre a cliente. Registra en historial."""
        tarjeta_id = self._sid(tarjeta_id)
        cliente_id = self._sid(cliente_id)
        try:
            tarjeta = self._load_tarjeta(tarjeta_id)
            if tarjeta.estado == "asignada":
                return AsignacionResult(
                    tarjeta_id, cliente_id, "asignacion",
                    False, f"Tarjeta ya asignada al cliente {tarjeta.id_cliente}"
                )
            if tarjeta.estado == "bloqueada":
                return AsignacionResult(
                    tarjeta_id, cliente_id, "asignacion",
                    False, "Tarjeta bloqueada, no se puede asignar"
                )

            accion = "reasignacion" if tarjeta.id_cliente else "asignacion"
            cliente_prev = tarjeta.id_cliente

            self.conn.execute(
                """
                UPDATE tarjetas_fidelidad
                SET id_cliente = ?, estado = 'asignada',
                    fecha_asignacion = datetime('now')
                WHERE id = ?
                """,
                (cliente_id, tarjeta_id)
            )
            self._log_asignacion(tarjeta_id, cliente_prev, cliente_id, accion, motivo)
            # Actualizar contadores del lote
            if tarjeta.batch_id:
                self._sync_contadores_lote(tarjeta.batch_id)
            self.conn.commit()

            logger.info("asignar_tarjeta id=%s cliente=%s", tarjeta_id, cliente_id)
            return AsignacionResult(tarjeta_id, cliente_id, accion, True, "Tarjeta asignada correctamente")

        except Exception as exc:
            logger.error("asignar_tarjeta: %s", exc)
            return AsignacionResult(tarjeta_id, cliente_id, "asignacion", False, str(exc))

    def liberar_tarjeta(self, tarjeta_id: str, motivo: str = "") -> AsignacionResult:
        """Desvincula tarjeta de cliente → estado libre."""
        tarjeta_id = self._sid(tarjeta_id)
        try:
            tarjeta = self._load_tarjeta(tarjeta_id)
            cliente_prev = tarjeta.id_cliente
            self.conn.execute(
                "UPDATE tarjetas_fidelidad SET id_cliente=NULL, estado='libre' WHERE id=?",
                (tarjeta_id,)
            )
            self._log_asignacion(tarjeta_id, cliente_prev, None, "liberacion", motivo)
            if tarjeta.batch_id:
                self._sync_contadores_lote(tarjeta.batch_id)
            self.conn.commit()
            return AsignacionResult(tarjeta_id, None, "liberacion", True, "Tarjeta liberada")
        except Exception as exc:
            return AsignacionResult(tarjeta_id, None, "liberacion", False, str(exc))

    def bloquear_tarjeta(
        self, tarjeta_id: str, motivo: str, bloqueado_por: str = None
    ) -> AsignacionResult:
        tarjeta_id = self._sid(tarjeta_id)
        bp = bloqueado_por or self.usuario
        try:
            tarjeta = self._load_tarjeta(tarjeta_id)
            self.conn.execute(
                "UPDATE tarjetas_fidelidad SET estado='bloqueada', activa=0, "
                "bloqueado_por=?, motivo_bloqueo=? WHERE id=?",
                (bp, motivo, tarjeta_id)
            )
            self._log_asignacion(tarjeta_id, tarjeta.id_cliente, tarjeta.id_cliente,
                                  "bloqueo", motivo)
            self.conn.commit()
            return AsignacionResult(tarjeta_id, None, "bloqueo", True, "Tarjeta bloqueada")
        except Exception as exc:
            return AsignacionResult(tarjeta_id, None, "bloqueo", False, str(exc))

    def desbloquear_tarjeta(self, tarjeta_id: str, motivo: str = "") -> AsignacionResult:
        tarjeta_id = self._sid(tarjeta_id)
        try:
            tarjeta = self._load_tarjeta(tarjeta_id)
            nuevo_estado = "asignada" if tarjeta.id_cliente else "libre"
            self.conn.execute(
                "UPDATE tarjetas_fidelidad SET estado=?, activa=1, "
                "bloqueado_por=NULL, motivo_bloqueo=NULL WHERE id=?",
                (nuevo_estado, tarjeta_id)
            )
            self._log_asignacion(tarjeta_id, tarjeta.id_cliente, tarjeta.id_cliente,
                                  "desbloqueo", motivo)
            self.conn.commit()
            return AsignacionResult(tarjeta_id, None, "desbloqueo", True, "Tarjeta desbloqueada")
        except Exception as exc:
            return AsignacionResult(tarjeta_id, None, "desbloqueo", False, str(exc))

    # ── Historial ─────────────────────────────────────────────────────────────

    def historial_tarjeta(self, tarjeta_id: str) -> List[dict]:
        rows = self.conn.execute(
            """
            SELECT h.accion, h.motivo, h.usuario, h.fecha,
                   c_prev.nombre AS cliente_prev,
                   c_new.nombre  AS cliente_nuevo
            FROM card_assignment_history h
            LEFT JOIN clientes c_prev ON c_prev.id = h.cliente_id_prev
            LEFT JOIN clientes c_new  ON c_new.id  = h.cliente_id_nuevo
            WHERE h.tarjeta_id = ?
            ORDER BY h.fecha DESC
            """,
            (str(tarjeta_id),)
        ).fetchall()
        return [
            {"accion": r[0], "motivo": r[1], "usuario": r[2], "fecha": r[3],
             "cliente_prev": r[4], "cliente_nuevo": r[5]}
            for r in rows
        ]

    def historial_cliente(self, cliente_id: str) -> List[dict]:
        rows = self.conn.execute(
            """
            SELECT h.accion, h.motivo, h.usuario, h.fecha,
                   tf.numero AS numero_tarjeta
            FROM card_assignment_history h
            JOIN tarjetas_fidelidad tf ON tf.id = h.tarjeta_id
            WHERE h.cliente_id_nuevo = ? OR h.cliente_id_prev = ?
            ORDER BY h.fecha DESC
            """,
            (str(cliente_id), str(cliente_id))
        ).fetchall()
        return [
            {"accion": r[0], "motivo": r[1], "usuario": r[2], "fecha": r[3],
             "numero_tarjeta": r[4]}
            for r in rows
        ]

    # ── QR Image ─────────────────────────────────────────────────────────────

    def generar_qr_imagen(self, numero: str, size_px: int = 200) -> Optional[bytes]:
        """Genera imagen PNG del QR en bytes. None si qrcode no disponible."""
        if not HAS_QR:
            return None
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(numero)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ── Exportar PDF lote ────────────────────────────────────────────────────

    def exportar_pdf_lote(
        self,
        batch_id:  str,
        ruta_pdf:  str,
        cols:      int = 6,
        rows_page: int = 4,
    ) -> int:
        """
        Genera PDF con todas las tarjetas del lote para imprenta.
        Cada tarjeta muestra: número, QR, nivel Bronce.
        Retorna cantidad de tarjetas incluidas.
        """
        if not HAS_REPORTLAB:
            raise RuntimeError("reportlab no instalado — no se puede generar PDF de lote")

        tarjetas = self.conn.execute(
            """
            SELECT numero, codigo_qr, COALESCE(nivel,'Bronce')
            FROM tarjetas_fidelidad
            WHERE batch_id = ?
            ORDER BY id
            """,
            (str(batch_id),)
        ).fetchall()

        if not tarjetas:
            raise ValueError(f"Batch {batch_id} sin tarjetas")

        batch = self._load_batch(batch_id)

        pagesize = (12 * inch, 18 * inch)
        c    = rl_canvas.Canvas(ruta_pdf, pagesize=pagesize)
        W, H = pagesize
        mg   = 10 * mm
        cell_w = (W - 2 * mg) / cols
        cell_h = (H - 2 * mg) / rows_page

        def dibujar_tarjeta(x, y, numero, qr_code, nivel):
            # Marco
            c.setStrokeColorRGB(0.2, 0.2, 0.2)
            c.setLineWidth(0.5)
            c.rect(x + 1*mm, y + 1*mm, cell_w - 2*mm, cell_h - 2*mm)
            # Número
            c.setFont("Helvetica-Bold", 7)
            c.setFillColor(HexColor("#ffc72c"))
            c.drawString(x + 3*mm, y + cell_h - 8*mm, numero)
            # Nivel
            c.setFont("Helvetica", 6)
            c.setFillColor(HexColor("#ffc72c"))
            c.drawString(x + 3*mm, y + cell_h - 13*mm, f"Nivel: {nivel}")
            # QR si disponible
            if HAS_QR and qr_code:
                try:
                    qr_img_data = self.generar_qr_imagen(numero, size_px=80)
                    if qr_img_data:
                        ir = ImageReader(io.BytesIO(qr_img_data))
                        qr_size = min(cell_w - 8*mm, cell_h - 20*mm)
                        c.drawImage(ir, x + (cell_w - qr_size)/2,
                                    y + 2*mm, qr_size, qr_size)
                except Exception:
                    c.setFont("Helvetica", 5)
                    c.setFillColor(HexColor("#ffc72c"))
                    c.drawString(x + 3*mm, y + cell_h/2, qr_code[:16])

        idx = 0
        col = 0
        row = 0

        for numero, qr_code, nivel in tarjetas:
            x = mg + col * cell_w
            y = H - mg - (row + 1) * cell_h
            dibujar_tarjeta(x, y, numero, qr_code, nivel)
            col += 1
            if col >= cols:
                col = 0
                row += 1
            if row >= rows_page:
                c.showPage()
                col = 0
                row = 0
            idx += 1

        if idx > 0:
            c.save()

        logger.info("exportar_pdf_lote batch=%d n=%d ruta=%s", batch_id, idx, ruta_pdf)
        return idx

    # ── Internos ──────────────────────────────────────────────────────────────

    def _log_asignacion(
        self,
        tarjeta_id:     str,
        cliente_prev:   Optional[str],
        cliente_nuevo:  Optional[str],
        accion:         str,
        motivo:         str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO card_assignment_history
                (tarjeta_id, cliente_id_prev, cliente_id_nuevo,
                 accion, motivo, usuario)
            VALUES (?,?,?,?,?,?)
            """,
            (self._sid(tarjeta_id), self._sid(cliente_prev), self._sid(cliente_nuevo),
             accion, motivo, self.usuario)
        )

    def _sync_contadores_lote(self, batch_id: str) -> None:
        row = self.conn.execute(
            """
        SELECT
                COUNT(*) FILTER (WHERE estado = 'libre'),
                COUNT(*) FILTER (WHERE estado = 'asignada')
            FROM tarjetas_fidelidad WHERE batch_id = ?
            """,
            (str(batch_id),)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE card_batches SET cantidad_libres=?, cantidad_asignadas=? WHERE id=?",
                (row[0], row[1], str(batch_id))
            )
