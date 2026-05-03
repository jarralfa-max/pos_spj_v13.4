
# repositories/cliente_repository.py — SPJ POS v12
"""
Repositorio de clientes.
Extrae toda la SQL de modulos/clientes.py a la capa de datos.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("spj.repo.clientes")


class ClienteRepository:
    def __init__(self, db_conn):
        self.db = db_conn

    # ── Consultas ────────────────────────────────────────────────────────────

    def get_by_id(self, cliente_id: int) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM clientes WHERE id=?", (cliente_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_codigo(self, codigo: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM clientes WHERE codigo_fidelidad=? OR telefono=?",
            (codigo, codigo)
        ).fetchone()
        return dict(row) if row else None

    def buscar(self, termino: str, limit: int = 50) -> list:
        q = f"%{termino}%"
        rows = self.db.execute("""
            SELECT id, nombre, telefono, email, puntos, codigo_fidelidad,
                   activo, fecha_registro
            FROM clientes
            WHERE (nombre LIKE ? OR telefono LIKE ? OR email LIKE ?
                   OR codigo_fidelidad LIKE ?)
              AND activo = 1
            ORDER BY nombre LIMIT ?
        """, (q, q, q, q, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_all(self, solo_activos: bool = True, limit: int = 200) -> list:
        sql = "SELECT * FROM clientes"
        if solo_activos:
            sql += " WHERE activo=1"
        sql += " ORDER BY nombre LIMIT ?"
        return [dict(r) for r in self.db.execute(sql, (limit,)).fetchall()]

    def contar(self, solo_activos: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM clientes"
        if solo_activos:
            sql += " WHERE activo=1"
        return self.db.execute(sql).fetchone()[0]

    def existe(self, cliente_id: int) -> bool:
        r = self.db.execute(
            "SELECT COUNT(*) FROM clientes WHERE id=?", (cliente_id,)
        ).fetchone()
        return r[0] > 0

    # ── Historial ────────────────────────────────────────────────────────────

    def get_historial_compras(self, cliente_id: int, limit: int = 30) -> list:
        try:
            rows = self.db.execute("""
                SELECT v.fecha, v.total, v.forma_pago, v.folio,
                       COALESCE(v.puntos_ganados, 0) AS puntos_ganados
                FROM ventas v
                WHERE v.cliente_id=? AND v.estado='completada'
                ORDER BY v.fecha DESC LIMIT ?
            """, (cliente_id, limit)).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_historial_compras(%d): %s", cliente_id, e)
            return []

    def get_movimientos_puntos(self, cliente_id: int, limit: int = 30) -> list:
        try:
            rows = self.db.execute("""
                SELECT fecha, tipo, puntos, saldo_actual, descripcion
                FROM puntos_fidelidad
                WHERE cliente_id=?
                ORDER BY fecha DESC LIMIT ?
            """, (cliente_id, limit)).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_movimientos_puntos(%d): %s", cliente_id, e)
            return []

    def get_stats(self, cliente_id: int) -> dict:
        """Devuelve estadísticas básicas del cliente."""
        try:
            row = self.db.execute("""
                SELECT COUNT(*) AS num_compras,
                       COALESCE(SUM(total), 0) AS total_gastado,
                       COALESCE(AVG(total), 0) AS ticket_promedio,
                       MAX(fecha) AS ultima_compra
                FROM ventas
                WHERE cliente_id=? AND estado='completada'
            """, (cliente_id,)).fetchone()
            return dict(row) if row else {}
        except Exception as e:
            logger.warning("get_stats(%d): %s", cliente_id, e)
            return {}

    # ── Mutaciones ───────────────────────────────────────────────────────────

    def crear(self, nombre: str, telefono: str = "", email: str = "",
              direccion: str = "", notas: str = "",
              codigo_fidelidad: str = None) -> int:
        if not nombre.strip():
            raise ValueError("nombre es obligatorio")
        cur = self.db.execute("""
            INSERT INTO clientes
                (nombre, telefono, email, direccion, notas,
                 codigo_qr, activo, fecha_alta)
            VALUES (?,?,?,?,?,?,1,datetime('now'))
        """, (nombre.strip(), telefono, email, direccion, notas, codigo_fidelidad))
        try: self.db.commit()
        except Exception: pass
        logger.info("Cliente creado id=%d nombre=%s", cur.lastrowid, nombre)
        return cur.lastrowid

    def actualizar(self, cliente_id: int, **campos) -> bool:
        if not campos:
            return False
        allowed = {"nombre","telefono","email","direccion","notas","activo"}
        campos_validos = {k: v for k, v in campos.items() if k in allowed}
        if not campos_validos:
            return False
        set_clause = ", ".join(f"{k}=?" for k in campos_validos)
        values = list(campos_validos.values()) + [cliente_id]
        self.db.execute(
            f"UPDATE clientes SET {set_clause} WHERE id=?", values
        )
        try: self.db.commit()
        except Exception: pass
        return True

    def dar_de_baja(self, cliente_id: int) -> bool:
        """Soft-delete: marca inactivo, preserva historial."""
        self.db.execute("""
            UPDATE clientes
            SET activo=0, fecha_inactivacion=date('now')
            WHERE id=?
        """, (cliente_id,))
        try: self.db.commit()
        except Exception: pass
        logger.info("Cliente %d dado de baja", cliente_id)
        return True

    def actualizar_puntos(self, cliente_id: int, nuevos_puntos: float) -> bool:
        self.db.execute(
            "UPDATE clientes SET puntos=? WHERE id=?",
            (nuevos_puntos, cliente_id)
        )
        try: self.db.commit()
        except Exception: pass
        return True
