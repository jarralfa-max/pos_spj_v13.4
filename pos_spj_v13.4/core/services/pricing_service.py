
# core/services/pricing_service.py — SPJ POS v10
"""
Gestion de listas de precios y descuentos por volumen.
  - Listas: Mostrador, Mayoreo, VIP, Empleados, Sucursal-X
  - Precio por cantidad: kg >= 10 -> precio especial
  - Precio por cliente (asignado a un cliente especifico)
  - Precio por sucursal
  - Herencia: Lista Mayoreo hereda de Lista Mostrador
"""
from __future__ import annotations
import logging
from core.db.connection import get_connection

logger = logging.getLogger("spj.pricing")


class PricingService:
    def __init__(self, conn=None):
        self.conn = conn or get_connection()
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS listas_precio (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT NOT NULL UNIQUE,
                descripcion TEXT,
                descuento_global DECIMAL(5,2) DEFAULT 0,
                hereda_de   INTEGER REFERENCES listas_precio(id),
                activa      INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS precios_lista (
                lista_id    INTEGER REFERENCES listas_precio(id) ON DELETE CASCADE,
                producto_id INTEGER REFERENCES productos(id),
                precio      DECIMAL(10,2) NOT NULL,
                PRIMARY KEY (lista_id, producto_id) ON CONFLICT REPLACE
            );
            CREATE TABLE IF NOT EXISTS precios_volumen (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id  INTEGER REFERENCES productos(id),
                lista_id     INTEGER REFERENCES listas_precio(id),
                cantidad_min DECIMAL(10,3) NOT NULL,
                precio       DECIMAL(10,2) NOT NULL,
                unidad       TEXT DEFAULT 'kg'
            );
            CREATE TABLE IF NOT EXISTS clientes_lista_precio (
                cliente_id  INTEGER PRIMARY KEY REFERENCES clientes(id),
                lista_id    INTEGER REFERENCES listas_precio(id)
            );
            CREATE INDEX IF NOT EXISTS idx_precios_lista_prod
                ON precios_lista(lista_id, producto_id);
            CREATE INDEX IF NOT EXISTS idx_vol_prod
                ON precios_volumen(producto_id, lista_id);
        """)
        # Seed listas base
        for nombre, desc in [
            ("Mostrador",  "Precio al publico general"),
            ("Mayoreo",    "Precio para compras grandes (>10kg)"),
            ("VIP",        "Precio especial clientes frecuentes"),
            ("Empleados",  "Precio interno para empleados"),
        ]:
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO listas_precio(nombre,descripcion) VALUES(?,?)",
                    (nombre, desc))
            except Exception:
                pass
        try: self.conn.commit()
        except Exception: pass

    # ── Consulta de precio ──────────────────────────────────────────────
    def get_precio(self, producto_id: int, cantidad: float = 1.0,
                   lista_id: int = None, cliente_id: int = None,
                   sucursal_id: int = 1) -> dict:
        """
        Retorna el mejor precio aplicable.
        Prioridad: precio_volumen > precio_lista_cliente > precio_lista > precio_base
        """
        # Determinar lista del cliente
        if cliente_id and not lista_id:
            row = self.conn.execute(
                "SELECT lista_id FROM clientes_lista_precio WHERE cliente_id=?",
                (cliente_id,)).fetchone()
            if row:
                lista_id = row[0]

        base = self._get_base_price(producto_id)
        precio_final = base
        fuente       = "base"

        # Precio de lista
        if lista_id:
            lp = self._get_list_price(producto_id, lista_id)
            if lp:
                precio_final = lp
                fuente       = f"lista:{lista_id}"

            # Precio por volumen (para carne cruda — kg)
            vp = self._get_volume_price(producto_id, cantidad, lista_id)
            if vp:
                precio_final = vp
                fuente       = f"volumen:lista{lista_id}:qty{cantidad}"

        descuento_pct = self._get_lista_descuento(lista_id) if lista_id else 0
        if descuento_pct and fuente == f"lista:{lista_id}":
            precio_final = round(precio_final * (1 - descuento_pct / 100), 4)

        return {
            "producto_id":  producto_id,
            "precio":       round(precio_final, 4),
            "precio_base":  base,
            "lista_id":     lista_id,
            "fuente":       fuente,
            "descuento_pct":descuento_pct,
        }

    def _get_base_price(self, prod_id: int) -> float:
        row = self.conn.execute(
            "SELECT precio FROM productos WHERE id=?", (prod_id,)).fetchone()
        return float(row[0]) if row else 0.0

    def _get_list_price(self, prod_id: int, lista_id: int) -> float | None:
        row = self.conn.execute(
            "SELECT precio FROM precios_lista WHERE lista_id=? AND producto_id=?",
            (lista_id, prod_id)).fetchone()
        if row:
            return float(row[0])
        # Intentar lista padre (herencia)
        parent = self.conn.execute(
            "SELECT hereda_de FROM listas_precio WHERE id=?", (lista_id,)).fetchone()
        if parent and parent[0]:
            return self._get_list_price(prod_id, parent[0])
        return None

    def _get_volume_price(self, prod_id: int, qty: float, lista_id: int) -> float | None:
        row = self.conn.execute("""
            SELECT precio FROM precios_volumen
            WHERE producto_id=? AND lista_id=? AND cantidad_min<=?
            ORDER BY cantidad_min DESC LIMIT 1""",
            (prod_id, lista_id, qty)).fetchone()
        return float(row[0]) if row else None

    def _get_lista_descuento(self, lista_id: int) -> float:
        row = self.conn.execute(
            "SELECT descuento_global FROM listas_precio WHERE id=?",
            (lista_id,)).fetchone()
        return float(row[0]) if row else 0.0

    # ── Gestion de listas ───────────────────────────────────────────────
    def get_listas(self) -> list:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM listas_precio ORDER BY id").fetchall()]

    def set_precio_lista(self, lista_id: int, producto_id: int, precio: float):
        self.conn.execute(
            "INSERT OR REPLACE INTO precios_lista(lista_id,producto_id,precio) VALUES(?,?,?)",
            (lista_id, producto_id, precio))
        try: self.conn.commit()
        except Exception: pass

    def set_precio_volumen(self, producto_id: int, lista_id: int,
                           cantidad_min: float, precio: float, unidad: str = "kg"):
        self.conn.execute("""
            INSERT OR REPLACE INTO precios_volumen
            (producto_id,lista_id,cantidad_min,precio,unidad) VALUES(?,?,?,?,?)""",
            (producto_id, lista_id, cantidad_min, precio, unidad))
        try: self.conn.commit()
        except Exception: pass

    def asignar_lista_cliente(self, cliente_id: int, lista_id: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO clientes_lista_precio(cliente_id,lista_id) VALUES(?,?)",
            (cliente_id, lista_id))
        try: self.conn.commit()
        except Exception: pass

    def get_precios_producto(self, producto_id: int) -> list:
        """Retorna todos los precios configurados para un producto."""
        rows = self.conn.execute("""
            SELECT l.nombre as lista, pl.precio, NULL as cant_min, NULL as unidad
            FROM precios_lista pl JOIN listas_precio l ON l.id=pl.lista_id
            WHERE pl.producto_id=?
            UNION ALL
            SELECT l.nombre, pv.precio, pv.cantidad_min, pv.unidad
            FROM precios_volumen pv JOIN listas_precio l ON l.id=pv.lista_id
            WHERE pv.producto_id=?
            ORDER BY 1""", (producto_id, producto_id)).fetchall()
        return [dict(r) for r in rows]
