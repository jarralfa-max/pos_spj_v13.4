
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
        self._clientes_columns_cache: set[str] | None = None

    def _get_clientes_columns(self) -> set[str]:
        if self._clientes_columns_cache is not None:
            return self._clientes_columns_cache
        try:
            rows = self.db.execute("PRAGMA table_info(clientes)").fetchall()
            cols = {str(r[1]) for r in rows}
        except Exception:
            cols = set()
        self._clientes_columns_cache = cols
        return cols

    def _has_clientes_column(self, column_name: str) -> bool:
        return column_name in self._get_clientes_columns()

    # ── Consultas ────────────────────────────────────────────────────────────

    def get_by_id(self, cliente_id: int) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM clientes WHERE id=?", (cliente_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_codigo(self, codigo: str) -> Optional[dict]:
        if self._has_clientes_column("codigo_fidelidad"):
            query = "SELECT * FROM clientes WHERE codigo_fidelidad=? OR telefono=?"
            params = (codigo, codigo)
        else:
            query = "SELECT * FROM clientes WHERE telefono=?"
            params = (codigo,)
        row = self.db.execute(query, params).fetchone()
        return dict(row) if row else None

    def buscar(self, termino: str, limit: int = 50) -> list:
        """Busca clientes activos por nombre, teléfono, email, qr o fidelidad."""
        q = f"%{termino}%"
        has_codigo_fidelidad = self._has_clientes_column("codigo_fidelidad")
        fidelidad_clause = " OR COALESCE(codigo_fidelidad,'') LIKE ?" if has_codigo_fidelidad else ""
        query = f"""
            SELECT *
            FROM clientes
            WHERE (nombre LIKE ? OR telefono LIKE ? OR email LIKE ?
                   OR COALESCE(codigo_qr,'') LIKE ?
                   {fidelidad_clause}
                   OR CAST(id AS TEXT) = ?)
              AND activo = 1
            ORDER BY nombre LIMIT ?
        """
        params = [q, q, q, q]
        if has_codigo_fidelidad:
            params.append(q)
        params.extend([termino, limit])
        rows = self.db.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def get_by_scanner(self, codigo: str) -> Optional[dict]:
        """Busca cliente activo por ID numérico, teléfono, código QR o código de fidelidad."""
        if self._has_clientes_column("codigo_fidelidad"):
            query = """SELECT * FROM clientes
               WHERE (CAST(id AS TEXT)=? OR telefono=? OR codigo_qr=? OR codigo_fidelidad=?)
                 AND activo=1 LIMIT 1"""
            params = (codigo, codigo, codigo, codigo)
        else:
            query = """SELECT * FROM clientes
               WHERE (CAST(id AS TEXT)=? OR telefono=? OR codigo_qr=?)
                 AND activo=1 LIMIT 1"""
            params = (codigo, codigo, codigo)
        row = self.db.execute(query, params).fetchone()
        return dict(row) if row else None

    def get_all(self, solo_activos: bool = True, limit: int = 200) -> list:
        sql = "SELECT * FROM clientes"
        if solo_activos:
            sql += " WHERE activo=1"
        sql += " ORDER BY nombre LIMIT ?"
        return [dict(r) for r in self.db.execute(sql, (limit,)).fetchall()]

    def get_filtered(self, filtro: str = "todos", limit: int = 500) -> list:
        """Get clientes with state filter: 'activos', 'inactivos', or 'todos'."""
        if filtro == "activos":
            sql = "WHERE activo=1"
        elif filtro == "inactivos":
            sql = "WHERE activo=0"
        else:
            sql = ""
        query = f"SELECT id, nombre, COALESCE(apellido,'') as apellido, telefono, puntos, nivel_fidelidad, COALESCE(saldo,0) as saldo, COALESCE(limite_credito,0) as limite_credito, COALESCE(activo,1) as activo FROM clientes {sql} ORDER BY nombre LIMIT ?"
        return [dict(r) for r in self.db.execute(query, (limit,)).fetchall()]

    def buscar_por_termino(self, termino: str, filtro: str = "todos", limit: int = 500) -> list:
        """Search clientes by name, phone, id or QR with state filter."""
        if filtro == "activos":
            estado_sql = "AND activo=1"
        elif filtro == "inactivos":
            estado_sql = "AND activo=0"
        else:
            estado_sql = ""

        if termino.startswith("CLI-") or termino.startswith("QR-"):
            codigo = termino.split('-')[-1] if '-' in termino else termino
            query = f"SELECT id, nombre, COALESCE(apellido,'') as apellido, telefono, puntos, nivel_fidelidad, COALESCE(saldo,0) as saldo, COALESCE(limite_credito,0) as limite_credito, COALESCE(activo,1) as activo FROM clientes WHERE (codigo_qr=? OR id=?) {estado_sql} ORDER BY nombre LIMIT ?"
            return [dict(r) for r in self.db.execute(query, (termino, codigo, limit)).fetchall()]
        else:
            like_param = f"%{termino}%"
            query = f"SELECT id, nombre, COALESCE(apellido,'') as apellido, telefono, puntos, nivel_fidelidad, COALESCE(saldo,0) as saldo, COALESCE(limite_credito,0) as limite_credito, COALESCE(activo,1) as activo FROM clientes WHERE (nombre LIKE ? OR COALESCE(apellido,'') LIKE ? OR telefono LIKE ? OR id=?) {estado_sql} ORDER BY nombre LIMIT ?"
            return [dict(r) for r in self.db.execute(query, (like_param, like_param, like_param, termino, limit)).fetchall()]

    def contar(self, solo_activos: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM clientes"
        if solo_activos:
            sql += " WHERE activo=1"
        return self.db.execute(sql).fetchone()[0]

    def get_stats_aggregate(self) -> dict:
        """Devuelve estadísticas agregadas: total, activos, con tarjeta, puntos totales."""
        row = self.db.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN activo=1 THEN 1 END) AS activos,
                COUNT(CASE WHEN codigo_qr IS NOT NULL AND activo=1 THEN 1 END) AS con_tarjeta,
                COALESCE(SUM(CASE WHEN activo=1 THEN puntos ELSE 0 END), 0) AS puntos_totales
            FROM clientes
        """).fetchone()
        return dict(row) if row else {"total": 0, "activos": 0, "con_tarjeta": 0, "puntos_totales": 0}

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
              codigo_fidelidad: str = None) -> str:
        if not nombre.strip():
            raise ValueError("nombre es obligatorio")
        from backend.shared.ids import new_uuid
        cliente_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        self.db.execute("""
            INSERT INTO clientes
                (id, nombre, telefono, email, direccion, notas,
                 codigo_qr, activo, fecha_alta)
            VALUES (?,?,?,?,?,?,?,1,datetime('now'))
        """, (cliente_id, nombre.strip(), telefono, email, direccion, notas, codigo_fidelidad))
        try: self.db.commit()
        except Exception: pass
        logger.info("Cliente creado id=%s nombre=%s", cliente_id, nombre)
        return cliente_id

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
