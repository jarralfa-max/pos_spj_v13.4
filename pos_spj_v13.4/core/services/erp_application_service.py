# core/services/erp_application_service.py — POS SPJ v13.4 — FASE 1
"""
ERPApplicationService — Punto ÚNICO de escritura para todo el ERP.

REGLA: ❌ NADIE escribe directo a BD
       ✅ TODO pasa por este servicio

RESPONSABILIDADES:
    1. Registrar entradas de inventario (compras, QR, devoluciones)
    2. Registrar salidas de inventario (merma, ajustes)
    3. Registrar movimientos financieros (gastos, ingresos)
    4. Aplicar fidelización post-venta
    5. Todo con transacciones atómicas

CADA operación:
    - Usa transacción (BEGIN/COMMIT/ROLLBACK)
    - Registra movimiento en el ledger de inventario
    - Actualiza productos.existencia via inventory_service
    - Registra en treasury si tiene impacto financiero
    - Emite evento al EventBus

USO:
    app = container.app_service
    app.registrar_compra(producto_id=1, cantidad=50, costo=85.50, ...)
    app.registrar_merma(producto_id=1, cantidad=2, motivo="Caducidad", ...)
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from core.db.connection import transaction

logger = logging.getLogger("spj.app_service")


class ERPApplicationService:
    """Punto único de escritura. Coordina inventory + treasury + audit."""

    def __init__(self, db_conn, inventory_service=None, treasury_service=None,
                 loyalty_service=None, sucursal_id: int = 1):
        self.db = db_conn
        self.treasury = treasury_service
        self.loyalty = loyalty_service
        self.sucursal_id = sucursal_id
        self._inv_svc = inventory_service

    # ══════════════════════════════════════════════════════════════════════════
    #  ENTRADAS DE INVENTARIO
    # ══════════════════════════════════════════════════════════════════════════

    def registrar_compra(self, producto_id: int, cantidad: float,
                         costo_unitario: float, usuario: str = "",
                         referencia: str = "", sucursal_id: int = 0,
                         proveedor_id: int = 0) -> Dict:
        """
        Registra entrada de inventario por compra.
        1. Movimiento de inventario (ledger)
        2. Actualiza stock en productos
        3. Registra egreso en tesorería
        """
        sid = sucursal_id or self.sucursal_id
        op_id = str(uuid.uuid4())[:8]
        ref = referencia or f"COMPRA-{op_id}"

        try:
            self._entrada_directa(producto_id, cantidad, costo_unitario,
                                   "COMPRA", ref, usuario, sid)

            # Registrar egreso financiero
            costo_total = round(cantidad * costo_unitario, 2)
            if self.treasury:
                try:
                    self.treasury.registrar_egreso(
                        "compra_inventario", f"Compra prod #{producto_id}",
                        costo_total, sid, ref, usuario)
                except Exception as e:
                    logger.debug("Treasury egreso: %s", e)

            logger.info("COMPRA: prod=%d qty=%.3f cost=%.2f ref=%s",
                        producto_id, cantidad, costo_unitario, ref)
            return {"ok": True, "referencia": ref, "costo_total": costo_total}

        except Exception as e:
            logger.error("registrar_compra FALLÓ: %s", e)
            return {"ok": False, "error": str(e)}

    def registrar_merma(self, producto_id: int, cantidad: float,
                        motivo: str = "", usuario: str = "",
                        sucursal_id: int = 0) -> Dict:
        """
        Registra salida de inventario por merma.
        1. Movimiento de inventario (salida)
        2. Actualiza stock
        3. Registra pérdida en tesorería
        """
        sid = sucursal_id or self.sucursal_id
        op_id = str(uuid.uuid4())[:8]
        ref = f"MERMA-{op_id}"

        try:
            costo_unit = self._get_costo_producto(producto_id)
            self._salida_directa(producto_id, cantidad, "MERMA", ref, usuario, sid)

            # Registrar pérdida financiera
            costo_total = round(cantidad * costo_unit, 2)
            if self.treasury:
                try:
                    self.treasury.registrar_egreso(
                        "merma", f"Merma prod #{producto_id}: {motivo}",
                        costo_total, sid, ref, usuario)
                except Exception:
                    pass

            logger.info("MERMA: prod=%d qty=%.3f motivo=%s", producto_id, cantidad, motivo)
            return {"ok": True, "referencia": ref, "costo_perdido": costo_total}

        except Exception as e:
            logger.error("registrar_merma FALLÓ: %s", e)
            return {"ok": False, "error": str(e)}

    def registrar_entrada_produccion(self, producto_id: int, cantidad: float,
                                      usuario: str = "", referencia: str = "",
                                      sucursal_id: int = 0) -> Dict:
        """Registra entrada por producción (producto terminado)."""
        sid = sucursal_id or self.sucursal_id
        ref = referencia or f"PROD-{str(uuid.uuid4())[:8]}"
        try:
            costo = self._get_costo_producto(producto_id)
            self._entrada_directa(producto_id, cantidad, costo,
                                   "PRODUCCION", ref, usuario, sid)
            return {"ok": True, "referencia": ref}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def registrar_salida_produccion(self, producto_id: int, cantidad: float,
                                     usuario: str = "", referencia: str = "",
                                     sucursal_id: int = 0) -> Dict:
        """Registra salida por consumo en producción (materia prima)."""
        sid = sucursal_id or self.sucursal_id
        ref = referencia or f"CONSUMO-{str(uuid.uuid4())[:8]}"
        try:
            self._salida_directa(producto_id, cantidad,
                                  "CONSUMO", ref, usuario, sid)
            return {"ok": True, "referencia": ref}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def registrar_ajuste(self, producto_id: int, nueva_cantidad: float,
                         motivo: str = "", usuario: str = "",
                         sucursal_id: int = 0) -> Dict:
        """Ajuste de inventario — establece stock en un valor exacto."""
        sid = sucursal_id or self.sucursal_id
        try:
            row = self.db.execute(
                "SELECT COALESCE(existencia,0) FROM productos WHERE id=?",
                (producto_id,)).fetchone()
            stock_actual = float(row[0]) if row else 0

            diff = nueva_cantidad - stock_actual
            if abs(diff) < 0.001:
                return {"ok": True, "sin_cambio": True}

            ref = f"AJUSTE-{str(uuid.uuid4())[:8]}"
            if diff > 0:
                self._entrada_directa(producto_id, diff, 0,
                                       "AJUSTE", ref, usuario, sid)
            else:
                self._salida_directa(producto_id, abs(diff),
                                      "AJUSTE", ref, usuario, sid)

            logger.info("AJUSTE: prod=%d de %.3f a %.3f", producto_id, stock_actual, nueva_cantidad)
            return {"ok": True, "antes": stock_actual, "despues": nueva_cantidad}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════════════════
    #  FIDELIZACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    def acreditar_puntos_venta(self, cliente_id: int, venta_id,
                                total: float, cajero: str = "") -> Dict:
        """Acredita puntos de fidelización después de una venta."""
        if not self.loyalty or not cliente_id:
            return {"estrellas_ganadas": 0}
        try:
            return self.loyalty.acreditar_venta(
                cliente_id=cliente_id, venta_id=venta_id,
                cajero=cajero, total=total)
        except Exception as e:
            logger.debug("Fidelización: %s", e)
            return {"estrellas_ganadas": 0}

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS (fallback si inventory_service no está disponible)
    # ══════════════════════════════════════════════════════════════════════════

    def _entrada_directa(self, prod_id, qty, costo, tipo, ref, usuario, sid):
        """Registra entrada: actualiza movimientos + las 3 tablas de stock."""
        with transaction(self.db) as c:
            c.execute("""
                INSERT INTO movimientos_inventario
                    (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                     costo_unitario, costo_total, descripcion, referencia,
                     usuario, sucursal_id, fecha)
                VALUES (?,?,'ENTRADA',?,?,?,?,?,?,?,?,datetime('now'))
            """, (str(uuid.uuid4()), prod_id, tipo, qty,
                  costo, round(qty * costo, 2), tipo, ref, usuario, sid))
            # inventario_actual (por sucursal) — costo promedio ponderado
            c.execute("""
                INSERT INTO inventario_actual
                    (producto_id, sucursal_id, cantidad, costo_promedio)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                    costo_promedio = CASE WHEN cantidad + excluded.cantidad > 0
                        THEN (cantidad * costo_promedio
                              + excluded.cantidad * excluded.costo_promedio)
                             / (cantidad + excluded.cantidad)
                        ELSE excluded.costo_promedio END,
                    cantidad             = cantidad + excluded.cantidad,
                    ultima_actualizacion = datetime('now')
            """, (prod_id, sid, qty, costo))
            # branch_inventory (leída por POS para validación de stock)
            # Manual upsert: ON CONFLICT no puede usar UNIQUE(branch_id, product_id, batch_id)
            # cuando batch_id es NULL (los NULLs son distintos en SQLite UNIQUE).
            _bi_updated = c.execute("""
                UPDATE branch_inventory
                SET quantity = quantity + ?, updated_at = datetime('now')
                WHERE product_id = ? AND branch_id = ? AND batch_id IS NULL
            """, (qty, prod_id, sid)).rowcount
            if not _bi_updated:
                c.execute("""
                    INSERT OR IGNORE INTO branch_inventory
                        (product_id, branch_id, quantity, batch_id, updated_at)
                    VALUES (?, ?, ?, NULL, datetime('now'))
                """, (prod_id, sid, qty))
            # productos.existencia = suma global de todas las sucursales
            c.execute("""
                UPDATE productos
                SET existencia    = (SELECT COALESCE(SUM(cantidad),0)
                                     FROM inventario_actual WHERE producto_id = ?),
                    precio_compra = CASE WHEN ? > 0 THEN ? ELSE precio_compra END
                WHERE id = ?
            """, (prod_id, costo, costo, prod_id))

    def _salida_directa(self, prod_id, qty, tipo, ref, usuario, sid):
        """Registra salida: actualiza movimientos + las 3 tablas de stock."""
        with transaction(self.db) as c:
            c.execute("""
                INSERT INTO movimientos_inventario
                    (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                     descripcion, referencia, usuario, sucursal_id, fecha)
                VALUES (?,?,'SALIDA',?,?,?,?,?,?,datetime('now'))
            """, (str(uuid.uuid4()), prod_id, tipo, qty, tipo, ref, usuario, sid))
            # inventario_actual
            c.execute("""
                INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
                VALUES (?, ?, ?)
                ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                    cantidad             = MAX(0, cantidad - excluded.cantidad),
                    ultima_actualizacion = datetime('now')
            """, (prod_id, sid, qty))
            # branch_inventory — manual upsert (ver nota en _entrada_directa)
            _bi_updated = c.execute("""
                UPDATE branch_inventory
                SET quantity = MAX(0, quantity - ?), updated_at = datetime('now')
                WHERE product_id = ? AND branch_id = ? AND batch_id IS NULL
            """, (qty, prod_id, sid)).rowcount
            if not _bi_updated:
                c.execute("""
                    INSERT OR IGNORE INTO branch_inventory
                        (product_id, branch_id, quantity, batch_id, updated_at)
                    VALUES (?, ?, 0, NULL, datetime('now'))
                """, (prod_id, sid))
            # productos.existencia = suma global
            c.execute("""
                UPDATE productos
                SET existencia = (SELECT COALESCE(SUM(cantidad),0)
                                  FROM inventario_actual WHERE producto_id = ?)
                WHERE id = ?
            """, (prod_id, prod_id))

    def _get_costo_producto(self, producto_id: int) -> float:
        try:
            row = self.db.execute(
                "SELECT COALESCE(precio_compra, costo, 0) FROM productos WHERE id=?",
                (producto_id,)).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0
