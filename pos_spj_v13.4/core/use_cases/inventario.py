# core/use_cases/inventario.py — SPJ POS v13.1
"""
Caso de uso: Gestionar Inventario

Orquesta operaciones de inventario con auditoría completa:
  - Entrada de mercancía (compra / recepción manual)
  - Salida por venta (delegada a ProcesarVentaUC)
  - Ajuste de inventario (merma, corrección)
  - Traspaso entre sucursales

Cada operación:
  1. Valida la operación
  2. Registra el movimiento con operation_id
  3. Actualiza stock
  4. Escribe en audit_logs
  5. Publica evento al EventBus
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger("spj.use_cases.inventario")


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class ResultadoInventario:
    ok:           bool
    operacion_id: str   = ""
    stock_nuevo:  float = 0.0
    error:        str   = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class GestionarInventarioUC:
    """
    Orquestador de operaciones de inventario.

    Uso:
        uc = GestionarInventarioUC.desde_container(container)
        r  = uc.registrar_entrada(producto_id=5, cantidad=10.0,
                                   sucursal_id=1, usuario="almacen",
                                   costo_unit=45.0, proveedor_id=3)
    """

    def __init__(self, db, inventory_service, event_bus=None):
        self._db  = db
        self._inv = inventory_service
        self._bus = event_bus

    @classmethod
    def desde_container(cls, container) -> "GestionarInventarioUC":
        return cls(
            db                = container.db,
            inventory_service = container.inventory_service,
            event_bus         = _get_bus(),
        )

    # ── Entrada de mercancía ──────────────────────────────────────────────────

    def registrar_entrada(
        self,
        producto_id:  int,
        cantidad:     float,
        sucursal_id:  int,
        usuario:      str,
        costo_unit:   float       = 0.0,
        proveedor_id: Optional[int] = None,
        referencia:   str         = "",
        notas:        str         = "",
    ) -> ResultadoInventario:
        if cantidad <= 0:
            return ResultadoInventario(ok=False, error="Cantidad debe ser > 0.")

        op_id = _gen_op_id()
        try:
            stock_antes = self._inv.get_stock(producto_id, sucursal_id)
            self._inv.add_stock(
                product_id    = producto_id,
                branch_id     = sucursal_id,
                qty           = cantidad,
                unit_cost     = costo_unit,
                reference_type = "ENTRADA" if not referencia else referencia,
                reference_id  = str(proveedor_id or ""),
                operation_id  = op_id,
                user          = usuario,
                notes         = notas,
            )
            stock_nuevo = self._inv.get_stock(producto_id, sucursal_id)
            self._audit("ENTRADA", producto_id, sucursal_id, usuario,
                        f"antes={stock_antes:.3f}", f"despues={stock_nuevo:.3f} (+{cantidad:.3f})",
                        op_id)
            self._bus_publish("AJUSTE_INVENTARIO", {
                "tipo":        "ENTRADA",
                "producto_id": producto_id,
                "sucursal_id": sucursal_id,
                "cantidad":    cantidad,
                "stock_nuevo": stock_nuevo,
                "usuario":     usuario,
                "op_id":       op_id,
            })
            return ResultadoInventario(ok=True, operacion_id=op_id, stock_nuevo=stock_nuevo)
        except Exception as e:
            logger.error("Entrada inventario prod=%s: %s", producto_id, e)
            return ResultadoInventario(ok=False, error=str(e))

    # ── Ajuste (merma / corrección) ───────────────────────────────────────────

    def registrar_ajuste(
        self,
        producto_id:  int,
        cantidad_nueva: float,
        sucursal_id:  int,
        usuario:      str,
        motivo:       str = "Ajuste manual",
    ) -> ResultadoInventario:
        op_id = _gen_op_id()
        try:
            stock_antes = self._inv.get_stock(producto_id, sucursal_id)
            delta = cantidad_nueva - stock_antes
            if delta > 0:
                self._inv.add_stock(
                    product_id=producto_id, branch_id=sucursal_id,
                    qty=delta, unit_cost=0.0,
                    reference_type="AJUSTE", reference_id="",
                    operation_id=op_id,
                    user=usuario, notes=motivo,
                )
            elif delta < 0:
                self._inv.deduct_stock(
                    product_id=producto_id, branch_id=sucursal_id,
                    qty=abs(delta),
                    reference_type="AJUSTE", reference_id="",
                    operation_id=op_id,
                    user=usuario, notes=motivo,
                )
            self._audit("AJUSTE", producto_id, sucursal_id, usuario,
                        str(stock_antes), str(cantidad_nueva), op_id)
            self._bus_publish("AJUSTE_INVENTARIO", {
                "tipo":        "AJUSTE",
                "producto_id": producto_id,
                "sucursal_id": sucursal_id,
                "stock_antes": stock_antes,
                "stock_nuevo": cantidad_nueva,
                "delta":       delta,
                "motivo":      motivo,
                "usuario":     usuario,
                "op_id":       op_id,
            })
            return ResultadoInventario(
                ok=True, operacion_id=op_id, stock_nuevo=cantidad_nueva
            )
        except Exception as e:
            logger.error("Ajuste inventario prod=%s: %s", producto_id, e)
            return ResultadoInventario(ok=False, error=str(e))

    # ── Traspaso entre sucursales ─────────────────────────────────────────────

    def registrar_traspaso(
        self,
        producto_id:    int,
        cantidad:       float,
        sucursal_origen: int,
        sucursal_destino: int,
        usuario:        str,
        notas:          str = "",
    ) -> ResultadoInventario:
        if sucursal_origen == sucursal_destino:
            return ResultadoInventario(ok=False, error="Origen y destino iguales.")
        if cantidad <= 0:
            return ResultadoInventario(ok=False, error="Cantidad debe ser > 0.")

        op_id = _gen_op_id()
        try:
            # Salida de origen
            self._inv.deduct_stock(
                product_id=producto_id, branch_id=sucursal_origen,
                qty=cantidad,
                reference_type="TRASPASO_SALIDA",
                reference_id=str(sucursal_destino),
                operation_id=op_id,
                user=usuario, notes=notas,
            )
            # Entrada en destino
            self._inv.add_stock(
                product_id=producto_id, branch_id=sucursal_destino,
                qty=cantidad, unit_cost=0.0,
                reference_type="TRASPASO_ENTRADA",
                reference_id=str(sucursal_origen),
                operation_id=op_id,
                user=usuario, notes=notas,
            )
            stock_nuevo = self._inv.get_stock(producto_id, sucursal_destino)
            self._audit("TRASPASO", producto_id, sucursal_origen, usuario,
                        f"suc={sucursal_origen} cant={cantidad}",
                        f"suc_dest={sucursal_destino}", op_id)
            self._bus_publish("TRASPASO_INICIADO", {
                "producto_id":      producto_id,
                "cantidad":         cantidad,
                "sucursal_origen":  sucursal_origen,
                "sucursal_destino": sucursal_destino,
                "usuario":          usuario,
                "op_id":            op_id,
            })
            return ResultadoInventario(ok=True, operacion_id=op_id, stock_nuevo=stock_nuevo)
        except Exception as e:
            logger.error("Traspaso prod=%s: %s", producto_id, e)
            return ResultadoInventario(ok=False, error=str(e))

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _audit(
        self,
        accion:   str,
        prod_id:  int,
        suc_id:   int,
        usuario:  str,
        val_antes: str,
        val_despues: str,
        op_id:    str,
    ) -> None:
        # Write to audit_logs (human-readable)
        try:
            self._db.execute(
                "INSERT INTO audit_logs"
                "(accion,modulo,entidad,entidad_id,usuario,sucursal_id,"
                " valor_antes,valor_despues,detalles,fecha)"
                " VALUES(?,?,?,?,?,?,?,?,?,datetime('now'))",
                (accion, "INVENTARIO", "productos", prod_id,
                 usuario, suc_id, val_antes, val_despues, op_id)
            )
        except Exception as e:
            logger.debug("audit_logs inventario: %s", e)

        # v13.2: Also write to event_log for sync
        try:
            from sync.event_logger import EventLogger
            el = EventLogger(self._db)
            el.registrar(
                tipo        = f"INVENTARIO_{accion}",
                entidad     = "productos",
                entidad_id  = prod_id,
                payload     = {
                    "accion":       accion,
                    "valor_antes":  val_antes,
                    "valor_despues":val_despues,
                    "operation_id": op_id,
                },
                sucursal_id  = suc_id,
                usuario      = usuario,
                operation_id = op_id,
            )
        except Exception as e:
            logger.debug("event_log inventario: %s", e)

        try:
            self._db.commit()
        except Exception:
            pass

    def _bus_publish(self, event: str, payload: dict) -> None:
        if self._bus:
            try:
                self._bus.publish(event, payload, async_=True)
            except Exception as e:
                logger.debug("EventBus %s: %s", event, e)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_op_id() -> str:
    return f"INV-{uuid.uuid4().hex[:12].upper()}"


def _get_bus():
    try:
        from core.events.event_bus import get_bus
        return get_bus()
    except Exception:
        return None
