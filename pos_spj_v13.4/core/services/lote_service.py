
# core/services/lote_service.py — SPJ POS v10
"""
Control de lotes y fechas de caducidad para carne en crudo.
FIFO automatico: las ventas descargan primero el lote mas antiguo.
Alertas: lotes a punto de caducar o ya caducados.
"""
from __future__ import annotations
from backend.shared.ids import new_uuid
import logging, uuid
from datetime import date, datetime, timedelta
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.lotes")

DIAS_ALERTA_CADUCIDAD = 3    # avisar si caduca en <= 3 dias


class LoteService:
    def __init__(self, conn=None, sucursal_id: int = 1, usuario: str = "system"):
        self.conn        = conn or get_connection()
        self.sucursal_id = sucursal_id
        self.usuario     = usuario
        self._init_tables()

    def _init_tables(self):
        pass  # Plan B born-clean: schema canónico en migrations/ (DDL removido)
        try: self.conn.commit()
        except Exception: pass

    # ── Ingreso de lote ────────────────────────────────────────────────
    def registrar_lote(self, producto_id: int, peso_kg: float,
                       fecha_caducidad: str = None, proveedor_id: int = None,
                       numero_lote: str = None, costo_kg: float = 0,
                       temperatura: float = None, observaciones: str = "") -> int:
        if not numero_lote:
            numero_lote = f"L{datetime.now().strftime('%Y%m%d%H%M%S')}"
        with transaction(self.conn) as c:
            lid = c.execute("""INSERT INTO lotes
                (uuid,producto_id,numero_lote,proveedor_id,peso_inicial_kg,
                 peso_actual_kg,costo_kg,fecha_caducidad,sucursal_id,
                 temperatura_c,observaciones)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (new_uuid(), producto_id, numero_lote, proveedor_id,
                 peso_kg, peso_kg, costo_kg, fecha_caducidad,
                 self.sucursal_id, temperatura, observaciones))
            lid = c.execute("SELECT id FROM lotes WHERE numero_lote=? AND producto_id=? ORDER BY rowid DESC LIMIT 1", (numero_lote, producto_id)).fetchone()[0]  # noqa: capture UUID just inserted
            c.execute("""INSERT INTO movimientos_lote
                (lote_id,tipo,cantidad_kg,referencia,usuario)
                VALUES(?,'recepcion',?,?,?)""",
                (lid, peso_kg, numero_lote, self.usuario))
            # Actualizar existencia del producto
            c.execute("UPDATE productos SET existencia=existencia+? WHERE id=?",
                      (peso_kg, producto_id))
        logger.info("Lote %s registrado: prod=%d %.3fkg caducidad=%s",
                    numero_lote, producto_id, peso_kg, fecha_caducidad)
        return lid

    # ── Descarga FIFO ────────────────────────────────────────────────
    def descargar_fifo(self, producto_id: int, cantidad_kg: float,
                       referencia: str = "", tipo: str = "venta") -> list:
        """
        Descarga cantidad_kg del producto usando FIFO
        (lote mas antiguo con fecha de caducidad mas proxima primero).
        Retorna lista de lotes afectados con cantidades.
        """
        pendiente = cantidad_kg
        afectados = []
        lotes = self.conn.execute("""
            SELECT id, peso_actual_kg, numero_lote, fecha_caducidad
            FROM lotes
            WHERE producto_id=? AND estado='activo' AND peso_actual_kg>0
            ORDER BY fecha_caducidad ASC NULLS LAST, fecha_recepcion ASC""",
            (producto_id,)).fetchall()

        with transaction(self.conn) as c:
            for lote in lotes:
                if pendiente <= 0:
                    break
                lid, disponible, num, caducidad = lote
                disponible = float(disponible)
                usar = min(pendiente, disponible)
                nuevo_peso = round(disponible - usar, 4)
                c.execute(
                    "UPDATE lotes SET peso_actual_kg=?, estado=CASE WHEN ?<=0 THEN 'agotado' ELSE estado END WHERE id=?",
                    (nuevo_peso, nuevo_peso, lid))
                c.execute("""INSERT INTO movimientos_lote
                    (lote_id,tipo,cantidad_kg,referencia,usuario) VALUES(?,?,?,?,?)""",
                    (lid, tipo, -usar, referencia, self.usuario))
                afectados.append({"lote_id": lid, "numero_lote": num,
                                   "cantidad_kg": usar, "caducidad": caducidad})
                pendiente = round(pendiente - usar, 4)

            if pendiente > 0.001:
                logger.warning("Stock insuficiente en lotes: prod=%d faltaron=%.3fkg",
                               producto_id, pendiente)
        return afectados

    # ── Alertas ─────────────────────────────────────────────────────
    def get_alertas_caducidad(self) -> list:
        """Lotes que caducan pronto o ya caducaron."""
        hoy    = date.today().isoformat()
        limite = (date.today() + timedelta(days=DIAS_ALERTA_CADUCIDAD)).isoformat()
        rows   = self.conn.execute("""
            SELECT l.*, p.nombre as producto_nombre
            FROM lotes l JOIN productos p ON p.id=l.producto_id
            WHERE l.estado='activo'
              AND l.fecha_caducidad IS NOT NULL
              AND l.fecha_caducidad <= ?
            ORDER BY l.fecha_caducidad ASC""", (limite,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            cad = d.get("fecha_caducidad","")
            d["vencido"]    = bool(cad and cad < hoy)
            d["dias_para_caducar"] = (
                (date.fromisoformat(cad) - date.today()).days
                if cad else None)
            result.append(d)
        return result

    def get_stock_por_lote(self, producto_id: int) -> list:
        rows = self.conn.execute("""
            SELECT l.*, p.nombre as producto_nombre
            FROM lotes l JOIN productos p ON p.id=l.producto_id
            WHERE l.producto_id=? AND l.estado='activo' AND l.peso_actual_kg>0
            ORDER BY l.fecha_caducidad ASC NULLS LAST""",
            (producto_id,)).fetchall()
        return [dict(r) for r in rows]

    def marcar_caducados(self) -> int:
        """Tarea nocturna: marca lotes vencidos automaticamente."""
        hoy = date.today().isoformat()
        affected = self.conn.execute(
            "UPDATE lotes SET estado='caducado' WHERE estado='activo' AND fecha_caducidad < ?",
            (hoy,)).rowcount
        try: self.conn.commit()
        except Exception: pass
        if affected:
            logger.warning("Lotes marcados como caducados: %d", affected)
        return affected

    def get_costo_promedio_ponderado(self, producto_id: int) -> float:
        """CAPP para valoracion de inventario."""
        row = self.conn.execute("""
            SELECT CASE WHEN SUM(peso_actual_kg)>0
                   THEN SUM(peso_actual_kg*costo_kg)/SUM(peso_actual_kg)
                   ELSE 0 END
            FROM lotes WHERE producto_id=? AND estado='activo'""",
            (producto_id,)).fetchone()
        return round(float(row[0]), 4) if row else 0.0
