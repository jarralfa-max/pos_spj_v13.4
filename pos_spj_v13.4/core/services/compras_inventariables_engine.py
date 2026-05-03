
# core/services/compras_inventariables_engine.py — SPJ POS v12
"""
Motor de compras de activos inventariables (equipos, herramientas, vehiculos).
Crea el registro en compras_inventariables y opcionalmente en activos_fijos.
"""
from __future__ import annotations
import logging, uuid
from datetime import datetime

logger = logging.getLogger("spj.compras_inventariables")


class ComprasInventariablesEngine:
    """
    Registra compras de bienes duraderos que se incorporan al balance
    como activos inventariables o activos fijos.
    """

    def __init__(self, conn, usuario: str = "admin", sucursal_id: int = 1):
        self.conn = conn
        self.usuario = usuario
        self.sucursal_id = sucursal_id
        self._init_tables()

    def _init_tables(self):
        try:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS compras_inventariables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
                    descripcion TEXT NOT NULL,
                    proveedor TEXT,
                    monto REAL NOT NULL,
                    metodo_pago TEXT DEFAULT 'Efectivo',
                    categoria TEXT DEFAULT 'equipamiento',
                    sucursal_id INTEGER DEFAULT 1,
                    usuario TEXT,
                    activo_fijo_id INTEGER,
                    notas TEXT,
                    fecha DATETIME DEFAULT (datetime('now'))
                );
            """)
            try: self.conn.commit()
            except Exception: pass
        except Exception as e:
            logger.debug("_init_tables: %s", e)

    def registrar(self, descripcion: str, monto: float,
                  proveedor: str = "", metodo_pago: str = "Efectivo",
                  categoria: str = "equipamiento", notas: str = "",
                  crear_activo_fijo: bool = False) -> dict:
        """
        Registra una compra de bien inventariable.
        Si crear_activo_fijo=True, crea adicionalmente el registro en activos_fijos.
        """
        if not descripcion.strip():
            raise ValueError("descripcion es obligatoria")
        if monto <= 0:
            raise ValueError("monto debe ser positivo")

        activo_fijo_id = None
        if crear_activo_fijo:
            activo_fijo_id = self._crear_activo_fijo(descripcion, monto, categoria, proveedor)

        cid = self.conn.execute("""
            INSERT INTO compras_inventariables
                (descripcion, proveedor, monto, metodo_pago, categoria,
                 sucursal_id, usuario, activo_fijo_id, notas)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (descripcion, proveedor, monto, metodo_pago, categoria,
              self.sucursal_id, self.usuario, activo_fijo_id, notas)).lastrowid

        try: self.conn.commit()
        except Exception: pass

        logger.info("Compra inventariable #%d: %s $%.2f", cid, descripcion, monto)
        return {
            "id": cid,
            "descripcion": descripcion,
            "monto": monto,
            "activo_fijo_id": activo_fijo_id,
        }

    def get_compras(self, categoria: str = None,
                    fecha_ini: str = None, fecha_fin: str = None,
                    limit: int = 50) -> list:
        sql = "SELECT * FROM compras_inventariables WHERE sucursal_id=?"
        params = [self.sucursal_id]
        if categoria:
            sql += " AND categoria=?"; params.append(categoria)
        if fecha_ini:
            sql += " AND DATE(fecha)>=?"; params.append(fecha_ini)
        if fecha_fin:
            sql += " AND DATE(fecha)<=?"; params.append(fecha_fin)
        sql += " ORDER BY fecha DESC LIMIT ?"; params.append(limit)
        try:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]
        except Exception as e:
            logger.warning("get_compras: %s", e); return []

    def _crear_activo_fijo(self, nombre: str, valor: float,
                            categoria: str, proveedor: str) -> int:
        try:
            row = self.conn.execute("""
                INSERT INTO activos_fijos
                    (nombre, categoria, valor_adquisicion, proveedor,
                     sucursal_id, fecha_adquisicion, estado, usuario)
                VALUES (?,?,?,?,?,DATE('now'),'activo',?)
            """, (nombre, categoria, valor, proveedor,
                  self.sucursal_id, self.usuario)).lastrowid
            return row
        except Exception as e:
            logger.debug("_crear_activo_fijo: %s — tabla puede no existir", e)
            return None
