
# delivery/asignacion_repartidor.py — SPJ POS v11
"""
Asignación de repartidores a pedidos.
  - Asignación manual o automática (por menos carga)
  - Actualización de estado en tiempo real
  - Registro de ubicación GPS (desde PWA)
"""
from __future__ import annotations
import logging
from datetime import datetime
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.delivery.asignacion")


class AsignacionRepartidor:
    def __init__(self, conn=None, sucursal_id: int = 1):
        self.conn        = conn or get_connection()
        self.sucursal_id = sucursal_id
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL, telefono TEXT, vehiculo TEXT,
                activo INTEGER DEFAULT 1, sucursal_id INTEGER DEFAULT 1,
                en_ruta INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS driver_locations (
                chofer_id INTEGER PRIMARY KEY,
                lat REAL, lng REAL, timestamp DATETIME
            );
        """)
        try: self.conn.commit()
        except Exception: pass

    # ── Repartidores ───────────────────────────────────────────────
    def get_repartidores_activos(self) -> list:
        rows = self.conn.execute("""
        SELECT d.*, COUNT(p.id) as pedidos_activos
            FROM drivers d
            LEFT JOIN pedidos_whatsapp p
                ON p.repartidor_id=d.id AND p.estado NOT IN ('entregado','cancelado')
            WHERE d.activo=1 AND d.sucursal_id=?
            GROUP BY d.id ORDER BY pedidos_activos ASC""",
            (self.sucursal_id,)).fetchall()
        return [dict(r) for r in rows]

    def asignar(self, pedido_id: int, repartidor_id: int,
                usuario: str = "admin") -> bool:
        try:
            with transaction(self.conn) as c:
                c.execute("""UPDATE pedidos_whatsapp
                    SET repartidor_id=?, estado='listo'
                    WHERE id=?""", (repartidor_id, pedido_id))
                c.execute("UPDATE drivers SET en_ruta=1 WHERE id=?",
                          (repartidor_id,))
            logger.info("Pedido #%d asignado a repartidor #%d", pedido_id, repartidor_id)
            return True
        except Exception as e:
            logger.error("asignar: %s", e)
            return False

    def asignar_automatico(self, pedido_id: int) -> int | None:
        """Asigna al repartidor con menos pedidos activos."""
        reps = self.get_repartidores_activos()
        if not reps:
            return None
        elegido = reps[0]["id"]
        self.asignar(pedido_id, elegido)
        return elegido

    def marcar_entregado(self, pedido_id: int, repartidor_id: int):
        with transaction(self.conn) as c:
            c.execute("""UPDATE pedidos_whatsapp
                SET estado='entregado', fecha_entrega=datetime('now')
                WHERE id=?""", (pedido_id,))
            # Verificar si el repartidor tiene más pedidos activos
            activos = c.execute("""
        SELECT COUNT(*) FROM pedidos_whatsapp
                WHERE repartidor_id=? AND estado NOT IN ('entregado','cancelado')""",
                (repartidor_id,)).fetchone()[0]
            if activos == 0:
                c.execute("UPDATE drivers SET en_ruta=0 WHERE id=?",
                          (repartidor_id,))

    def actualizar_ubicacion(self, chofer_id: int, lat: float, lng: float):
        self.conn.execute("""INSERT OR REPLACE INTO driver_locations
            (chofer_id, lat, lng, timestamp) VALUES(?,?,?,datetime('now'))""",
            (chofer_id, lat, lng))
        try: self.conn.commit()
        except Exception: pass

    def get_ubicacion(self, chofer_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM driver_locations WHERE chofer_id=?",
            (chofer_id,)).fetchone()
        return dict(row) if row else None

    def get_pedidos_repartidor(self, repartidor_id: int) -> list:
        rows = self.conn.execute("""
            SELECT p.*, d.nombre as repartidor_nombre
            FROM pedidos_whatsapp p
            LEFT JOIN drivers d ON d.id=p.repartidor_id
            WHERE p.repartidor_id=? AND p.estado IN ('listo','confirmado')
            ORDER BY p.fecha DESC""", (repartidor_id,)).fetchall()
        return [dict(r) for r in rows]
