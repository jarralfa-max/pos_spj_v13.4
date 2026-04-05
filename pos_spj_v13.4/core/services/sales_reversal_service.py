
# core/services/sales_reversal_service.py
# ── SalesReversalService — Cancelaciones, Devoluciones, Notas de Crédito ─────
#
# PRINCIPIO FUNDAMENTAL:
#   ❌ NUNCA borrar ventas, pagos, movimientos ni históricos
#   ✔  Todo se revierte con movimientos compensatorios (modelo contable real)
#   ✔  Cada operación es atómica: BEGIN IMMEDIATE → pasos → COMMIT o ROLLBACK total
#   ✔  Sin estados intermedios observables desde fuera de la transacción
#
# MÉTODOS PÚBLICOS:
#   cancel_sale(sale_id, usuario)
#   refund_items(sale_id, items, usuario)
#   issue_credit_note(sale_id, amount, reason, usuario)
#
# PROHIBIDO DESDE AFUERA:
#   Llamar a InventoryEngine directamente para reversiones
#   INSERT en movimientos_caja directamente para reversiones
#   UPDATE directos sobre ventas, detalles_venta, payments
#
# Versión: 1.0 — Fase 3 hardening
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from core.services.inventory_engine import (
    InventoryEngine,
    StockInsuficienteError,
)

logger = logging.getLogger("spj.sales_reversal_service")

CENTAVO = Decimal("0.01")


# ── Excepciones ───────────────────────────────────────────────────────────────

class ReversalError(Exception):
    """Error base de reversión."""


class VentaNoEncontradaError(ReversalError):
    """La venta no existe."""


class VentaNoCompletadaError(ReversalError):
    """La venta no está en estado 'completada'."""


class VentaYaCanceladaError(ReversalError):
    """La venta ya fue cancelada."""


class DevolucionExcedeError(ReversalError):
    """Cantidad a devolver supera la vendida o ya devuelta."""


class CreditNoteExcedeError(ReversalError):
    """Importe de nota de crédito supera el total neto de la venta."""


class UsuarioRequeridoError(ReversalError):
    """El campo usuario es obligatorio."""


class OperacionSinItemsError(ReversalError):
    """La lista de ítems para devolución está vacía."""


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class RefundItemDTO:
    """Un ítem a devolver parcial o totalmente."""
    sale_item_id: int      # detalles_venta.id
    quantity:     float    # cantidad a devolver
    reason:       str = ""


@dataclass
class CancelResultDTO:
    sale_id:      int
    operation_id: str
    total_revertido: float
    inventario_restaurado: int   # cantidad de ítems restaurados


@dataclass
class RefundResultDTO:
    sale_id:      int
    operation_id: str
    refund_ids:   List[int]
    total_devuelto: float
    inventario_restaurado: int


@dataclass
class CreditNoteResultDTO:
    sale_id:         int
    credit_note_id:  int
    operation_id:    str
    amount:          float
    reason:          str


# ══════════════════════════════════════════════════════════════════════════════

class SalesReversalService:
    """
    Único punto de entrada para cancelaciones, devoluciones y notas de crédito.

    Garantías por operación:
        cancel_sale      → inventario restaurado + caja compensada + venta cancelada (atómico)
        refund_items     → inventario parcial + caja compensada + refund registrado (atómico)
        issue_credit_note → caja compensada + nota registrada (atómico, sin inventario)

    En todos los casos:
        ✔ Si falla cualquier paso → ROLLBACK TOTAL
        ✔ Ningún histórico se modifica
        ✔ Cada operación genera un operation_id único (nunca reutilizado)
        ✔ La auditoría puede reconstruir el estado exacto en cualquier punto del tiempo
    """

    def __init__(self, db, branch_id: int):
        """
        db        — instancia de core.database.Database
        branch_id — sucursal activa
        """
        self.db = db
        self.branch_id = branch_id

    # ── Helpers internos ─────────────────────────────────────────────────────

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def _get_venta(self, conn, sale_id: int) -> dict:
        row = conn.execute("SELECT * FROM ventas WHERE id = ?", (sale_id,)).fetchone()
        if not row:
            raise VentaNoEncontradaError(f"VENTA_NO_ENCONTRADA: id={sale_id}")
        return dict(row)

    def _get_items(self, conn, sale_id: int) -> List[dict]:
        rows = conn.execute(
            "SELECT * FROM detalles_venta WHERE venta_id = ?", (sale_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_caja_abierta(self, conn, branch_id: int) -> Optional[int]:
        row = conn.execute("""
            SELECT id FROM cajas
            WHERE sucursal_id = ? AND estado = 'ABIERTA'
            ORDER BY fecha_apertura DESC LIMIT 1
        """, (branch_id,)).fetchone()
        return row["id"] if row else None

    def _get_payment_method(self, conn, sale_id: int) -> str:
        """Obtiene el método de pago principal de la venta."""
        row = conn.execute(
            "SELECT method FROM payments WHERE venta_id = ? ORDER BY id ASC LIMIT 1",
            (sale_id,)
        ).fetchone()
        if row:
            return row["method"]
        # Fallback a forma_pago en ventas
        row2 = conn.execute("SELECT forma_pago FROM ventas WHERE id = ?", (sale_id,)).fetchone()
        return row2["forma_pago"] if row2 else "Efectivo"

    def _insertar_movimiento_caja(self, conn, tipo: str, monto: float,
                                   descripcion: str, usuario: str,
                                   venta_id: int, forma_pago: str,
                                   operation_id: str,
                                   caja_id: Optional[int],
                                   reference_id: Optional[int] = None,
                                   reference_type: Optional[str] = None) -> int:
        """
        Inserta movimiento compensatorio en movimientos_caja.
        El monto puede ser negativo para representar salidas/reversiones.
        NO modifica ningún movimiento histórico existente.
        """
        conn.execute("""
            INSERT INTO movimientos_caja (
                tipo, monto, descripcion, usuario,
                venta_id, forma_pago, caja_id,
                reference_id, reference_type, operation_id, fecha
            ) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
        """, (
            tipo, monto, descripcion, usuario,
            venta_id, forma_pago, caja_id,
            reference_id, reference_type, operation_id,
        ))
        mov_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Actualizar saldo_actual de caja si está abierta
        if caja_id and monto != 0:
            conn.execute(
                "UPDATE cajas SET saldo_actual = saldo_actual + ? WHERE id = ?",
                (monto, caja_id)
            )
        return mov_id

    # ═════════════════════════════════════════════════════════════════════════
    # 1. CANCELACIÓN TOTAL
    # ═════════════════════════════════════════════════════════════════════════

    def cancel_sale(self, sale_id: int, usuario: str) -> CancelResultDTO:
        """
        Cancela totalmente una venta completada.

        Flujo atómico (BEGIN IMMEDIATE):
            1. Validar: venta existe, está 'completada', no cancelada antes
            2. Marcar venta como 'CANCEL_PENDING' (estado transitorio atómico)
            3. Revertir inventario ítem por ítem vía InventoryEngine(conn=conn)
            4. Insertar movimiento compensatorio de caja (SALE_CANCEL_OUT, monto negativo)
            5. Revertir puntos de fidelidad si aplica
            6. Marcar venta como 'cancelada'
            COMMIT

        Garantías:
            ✔ CANCEL_PENDING solo existe dentro de BEGIN IMMEDIATE — nunca visible desde afuera
            ✔ Inventario restaurado solo si la venta queda cancelada
            ✔ Movimientos originales no se tocan
            ✔ No se puede cancelar dos veces (trigger trg_block_double_cancel)
        """
        if not usuario or not usuario.strip():
            raise UsuarioRequeridoError("usuario es obligatorio")

        operation_id = f"CANCEL-{sale_id}-{uuid.uuid4().hex[:8]}"

        with self.db.transaction("SALE_CANCEL") as _:
            conn = self.db.conn

            # ── PASO 1: Validaciones ──────────────────────────────────────────
            venta = self._get_venta(conn, sale_id)

            if venta["estado"] == "cancelada":
                raise VentaYaCanceladaError(f"VENTA_YA_CANCELADA: id={sale_id}")
            if venta["estado"] != "completada":
                raise VentaNoCompletadaError(
                    f"VENTA_NO_COMPLETADA: id={sale_id} estado={venta['estado']}"
                )

            items = self._get_items(conn, sale_id)
            branch_id = venta["sucursal_id"]
            total = float(venta["total"])
            caja_id = self._get_caja_abierta(conn, branch_id)
            forma_pago = self._get_payment_method(conn, sale_id)

            # ── PASO 2: Marcar CANCEL_PENDING ─────────────────────────────────
            # Solo visible dentro de esta transacción.
            # El trigger trg_protect_sale_estado permite esta transición.
            conn.execute(
                "UPDATE ventas SET estado = 'CANCEL_PENDING' WHERE id = ?",
                (sale_id,)
            )

            # ── PASO 3: Revertir inventario ───────────────────────────────────
            inv_engine = InventoryEngine(self.db, branch_id, usuario)
            items_restaurados = 0

            for item in items:
                qty = float(item["cantidad"])
                prod_id = item["producto_id"]
                batch_id = item.get("batch_id")

                inv_engine.process_movement(
                    product_id=prod_id,
                    branch_id=branch_id,
                    quantity=+qty,
                    movement_type="SALE_CANCEL",
                    operation_id=f"{operation_id}_prod_{prod_id}",
                    batch_id=batch_id,
                    reference_id=sale_id,
                    reference_type="VENTA_CANCEL",
                    conn=conn,   # ← misma transacción, sin BEGIN propio
                )
                items_restaurados += 1

            # ── PASO 4: Movimiento compensatorio de caja ──────────────────────
            # Monto negativo = salida de caja (se devuelve dinero al cliente)
            self._insertar_movimiento_caja(
                conn=conn,
                tipo="SALE_CANCEL_OUT",
                monto=-total,
                descripcion=f"Cancelación venta #{venta['folio']}",
                usuario=usuario,
                venta_id=sale_id,
                forma_pago=forma_pago,
                operation_id=operation_id,
                caja_id=caja_id,
                reference_type="VENTA_CANCEL",
            )

            # ── PASO 5: Revertir puntos de fidelidad ──────────────────────────
            cliente_id = venta.get("cliente_id")
            puntos = int(venta.get("puntos_ganados") or 0)
            if cliente_id and puntos > 0:
                conn.execute(
                    "UPDATE clientes SET puntos = MAX(0, puntos - ?) WHERE id = ?",
                    (puntos, cliente_id)
                )
                conn.execute("""
                    INSERT INTO historico_puntos
                        (cliente_id, tipo, puntos, descripcion, saldo_actual, usuario, venta_id)
                    SELECT ?, 'CANCELACION', ?, ?,
                           MAX(0, puntos - ?), ?, ?
                    FROM clientes WHERE id = ?
                """, (
                    cliente_id, -puntos,
                    f"Cancelación venta {venta['folio']}",
                    puntos, usuario, sale_id, cliente_id,
                ))

            # ── PASO 6: Marcar cancelada (fin de transacción) ─────────────────
            conn.execute(
                "UPDATE ventas SET estado = 'cancelada' WHERE id = ?",
                (sale_id,)
            )

        # COMMIT automático al salir del with

        logger.info(
            "VENTA_CANCELADA id=%d folio=%s total=%.2f items=%d op=%s",
            sale_id, venta["folio"], total, items_restaurados, operation_id,
        )

        self._fire_event("VENTA_CANCELADA", {
            "sale_id": sale_id,
            "folio": venta["folio"],
            "total": total,
            "operation_id": operation_id,
        })

        return CancelResultDTO(
            sale_id=sale_id,
            operation_id=operation_id,
            total_revertido=total,
            inventario_restaurado=items_restaurados,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # 2. DEVOLUCIÓN PARCIAL
    # ═════════════════════════════════════════════════════════════════════════

    def refund_items(
        self,
        sale_id: int,
        items: List[RefundItemDTO],
        usuario: str,
        method: str = "Efectivo",
    ) -> RefundResultDTO:
        """
        Devuelve parcialmente ítems de una venta completada.

        items: lista de RefundItemDTO con sale_item_id y quantity a devolver.
        method: forma de devolución ('Efectivo', 'Tarjeta', 'Crédito').

        Flujo atómico (BEGIN IMMEDIATE):
            1. Validar: venta completada, cantidades no exceden lo vendido/ya devuelto
            2. INSERT sale_refunds por cada ítem
            3. Restaurar inventario vía InventoryEngine(conn=conn)
            4. Movimiento de caja compensatorio según método de pago
            COMMIT

        Reglas:
            ✔ SUM(refunds anteriores) + nueva_cantidad <= cantidad_vendida
            ✔ Si method='Efectivo' → SALE_REFUND_OUT (monto negativo en caja)
            ✔ Si method='Tarjeta'  → SALE_REFUND_PENDING (no simula reversión bancaria)
            ✔ Trigger trg_refund_no_excede como segunda línea de defensa en DB
        """
        if not usuario or not usuario.strip():
            raise UsuarioRequeridoError("usuario es obligatorio")
        if not items:
            raise OperacionSinItemsError("La lista de ítems para devolución está vacía")

        operation_id = f"REFUND-{sale_id}-{uuid.uuid4().hex[:8]}"

        with self.db.transaction("SALE_REFUND") as _:
            conn = self.db.conn

            # ── PASO 1: Validaciones ──────────────────────────────────────────
            venta = self._get_venta(conn, sale_id)
            if venta["estado"] == "cancelada":
                raise VentaYaCanceladaError(
                    f"REFUND_IMPOSIBLE: venta {sale_id} ya está cancelada"
                )
            if venta["estado"] not in ("completada",):
                raise VentaNoCompletadaError(
                    f"REFUND_IMPOSIBLE: venta {sale_id} estado={venta['estado']}"
                )

            branch_id = venta["sucursal_id"]
            caja_id = self._get_caja_abierta(conn, branch_id)
            inv_engine = InventoryEngine(self.db, branch_id, usuario)

            total_devuelto = Decimal("0")
            refund_ids = []

            for ref_item in items:
                # Obtener detalle original
                orig_row = conn.execute(
                    "SELECT * FROM detalles_venta WHERE id = ?",
                    (ref_item.sale_item_id,)
                ).fetchone()
                if not orig_row:
                    raise ReversalError(
                        f"DETALLE_NO_ENCONTRADO: sale_item_id={ref_item.sale_item_id}"
                    )
                orig = dict(orig_row)
                if orig["venta_id"] != sale_id:
                    raise ReversalError(
                        f"ITEM_NO_PERTENECE_A_VENTA: item={ref_item.sale_item_id} venta={sale_id}"
                    )

                qty_vendida = float(orig["cantidad"])
                qty_a_devolver = float(ref_item.quantity)

                if qty_a_devolver <= 0:
                    raise ReversalError(
                        f"CANTIDAD_INVALIDA: quantity={qty_a_devolver} debe ser positiva"
                    )

                # Calcular ya devuelto para este ítem
                ya_devuelto = conn.execute(
                    "SELECT COALESCE(SUM(quantity), 0) FROM sale_refunds WHERE sale_item_id = ?",
                    (ref_item.sale_item_id,)
                ).fetchone()[0]
                ya_devuelto = float(ya_devuelto)

                if ya_devuelto + qty_a_devolver > qty_vendida + 0.001:
                    raise DevolucionExcedeError(
                        f"DEVOLUCION_EXCEDE: item={ref_item.sale_item_id} "
                        f"vendido={qty_vendida:.4f} ya_devuelto={ya_devuelto:.4f} "
                        f"nuevo={qty_a_devolver:.4f} total_superaria={ya_devuelto + qty_a_devolver:.4f}"
                    )

                # Calcular monto proporcional
                precio_u = float(orig["precio_unitario"])
                descuento_u = float(orig.get("descuento") or 0) / qty_vendida if qty_vendida > 0 else 0
                amount = round((precio_u - descuento_u) * qty_a_devolver, 4)
                total_devuelto += Decimal(str(amount))

                # ── PASO 2: INSERT sale_refunds ───────────────────────────────
                conn.execute("""
                    INSERT INTO sale_refunds (
                        sale_id, sale_item_id, product_id,
                        quantity, amount, method,
                        reason, operation_id, created_by
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    sale_id, ref_item.sale_item_id, orig["producto_id"],
                    qty_a_devolver, amount, method,
                    ref_item.reason or "", operation_id, usuario,
                ))
                refund_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                refund_ids.append(refund_id)

                # ── PASO 3: Restaurar inventario ──────────────────────────────
                batch_id = orig.get("batch_id")
                inv_engine.process_movement(
                    product_id=orig["producto_id"],
                    branch_id=branch_id,
                    quantity=+qty_a_devolver,
                    movement_type="PARTIAL_REFUND",
                    operation_id=f"{operation_id}_item_{ref_item.sale_item_id}",
                    batch_id=batch_id,
                    reference_id=sale_id,
                    reference_type="VENTA_REFUND",
                    conn=conn,
                )

            total_f = float(total_devuelto.quantize(CENTAVO, ROUND_HALF_UP))

            # ── PASO 4: Movimiento compensatorio de caja ──────────────────────
            if method == "Efectivo":
                # Devolución en efectivo: sale dinero de la caja
                tipo_caja = "SALE_REFUND_OUT"
                monto_caja = -total_f
            else:
                # Tarjeta/Crédito: registrar como pendiente, no simular reversión bancaria
                tipo_caja = "SALE_REFUND_PENDING"
                monto_caja = 0.0   # no afecta saldo_actual de caja física

            self._insertar_movimiento_caja(
                conn=conn,
                tipo=tipo_caja,
                monto=monto_caja,
                descripcion=f"Devolución parcial venta #{venta['folio']}",
                usuario=usuario,
                venta_id=sale_id,
                forma_pago=method,
                operation_id=operation_id,
                caja_id=caja_id,
                reference_type="VENTA_REFUND",
            )

        # COMMIT automático

        logger.info(
            "DEVOLUCION_PARCIAL id=%d items=%d total_devuelto=%.2f op=%s",
            sale_id, len(refund_ids), total_f, operation_id,
        )

        return RefundResultDTO(
            sale_id=sale_id,
            operation_id=operation_id,
            refund_ids=refund_ids,
            total_devuelto=total_f,
            inventario_restaurado=len(refund_ids),
        )

    # ═════════════════════════════════════════════════════════════════════════
    # 3. NOTA DE CRÉDITO
    # ═════════════════════════════════════════════════════════════════════════

    def issue_credit_note(
        self,
        sale_id: int,
        amount: float,
        reason: str,
        usuario: str,
        method: str = "Efectivo",
    ) -> CreditNoteResultDTO:
        """
        Emite nota de crédito: ajuste financiero SIN movimiento de inventario.
        Casos: error de precio, bonificación, garantía, descuento post-venta.

        El importe no puede superar el total neto de la venta
        (total - refunds anteriores - notas de crédito anteriores).

        Flujo atómico (BEGIN IMMEDIATE):
            1. Validar: venta existe, monto no excede neto disponible
            2. INSERT credit_notes
            3. INSERT movimientos_caja (compensatorio, monto negativo)
            COMMIT

        NO mueve inventario.
        """
        if not usuario or not usuario.strip():
            raise UsuarioRequeridoError("usuario es obligatorio")
        if not reason or not reason.strip():
            raise ReversalError("reason es obligatorio para nota de crédito")
        if amount <= 0:
            raise ReversalError(f"MONTO_INVALIDO: amount={amount} debe ser positivo")

        operation_id = f"CREDIT-{sale_id}-{uuid.uuid4().hex[:8]}"

        with self.db.transaction("CREDIT_NOTE") as _:
            conn = self.db.conn

            # ── PASO 1: Validaciones ──────────────────────────────────────────
            venta = self._get_venta(conn, sale_id)
            if venta["estado"] == "cancelada":
                raise VentaYaCanceladaError(
                    f"CREDIT_NOTE_IMPOSIBLE: venta {sale_id} ya cancelada"
                )

            total_venta = float(venta["total"])

            # Neto disponible = total - refunds - notas de crédito previas
            total_refunds = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM sale_refunds WHERE sale_id = ?",
                (sale_id,)
            ).fetchone()[0]

            total_notas = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM credit_notes WHERE sale_id = ?",
                (sale_id,)
            ).fetchone()[0]

            neto_disponible = total_venta - float(total_refunds) - float(total_notas)

            if amount > neto_disponible + 0.01:
                raise CreditNoteExcedeError(
                    f"NOTA_CREDITO_EXCEDE: amount={amount:.2f} "
                    f"neto_disponible={neto_disponible:.2f} "
                    f"(total={total_venta:.2f} - refunds={float(total_refunds):.2f} "
                    f"- notas_previas={float(total_notas):.2f})"
                )

            caja_id = self._get_caja_abierta(conn, venta["sucursal_id"])

            # ── PASO 2: INSERT credit_notes ───────────────────────────────────
            conn.execute("""
                INSERT INTO credit_notes (sale_id, amount, reason, operation_id, created_by)
                VALUES (?,?,?,?,?)
            """, (sale_id, amount, reason.strip(), operation_id, usuario))
            credit_note_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # ── PASO 3: Movimiento compensatorio de caja ──────────────────────
            # Nota de crédito = salida de dinero sin devolución de producto
            if method == "Efectivo":
                monto_caja = -amount
                tipo_caja = "CREDIT_NOTE_OUT"
            else:
                monto_caja = 0.0        # no afecta caja física para tarjeta
                tipo_caja = "CREDIT_NOTE_PENDING"

            self._insertar_movimiento_caja(
                conn=conn,
                tipo=tipo_caja,
                monto=monto_caja,
                descripcion=f"Nota de crédito venta #{venta['folio']}: {reason[:60]}",
                usuario=usuario,
                venta_id=sale_id,
                forma_pago=method,
                operation_id=operation_id,
                caja_id=caja_id,
                reference_id=credit_note_id,
                reference_type="CREDIT_NOTE",
            )

        # COMMIT automático

        logger.info(
            "NOTA_CREDITO id=%d credit_note_id=%d amount=%.2f reason=%s op=%s",
            sale_id, credit_note_id, amount, reason[:40], operation_id,
        )

        return CreditNoteResultDTO(
            sale_id=sale_id,
            credit_note_id=credit_note_id,
            operation_id=operation_id,
            amount=amount,
            reason=reason,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # 4. AUDITORÍA — resumen matemáticamente consistente
    # ═════════════════════════════════════════════════════════════════════════

    def get_sale_audit(self, sale_id: int) -> dict:
        """
        Reconstruye el estado completo de una venta para auditoría.

        Retorna:
        {
            venta: {...},
            items: [...],
            payments: [...],
            inventory_movements: [...],
            caja_movements: [...],
            refunds: [...],
            credit_notes: [...],
            balance: {
                total_original, total_refunds, total_credit_notes, neto_real,
                inventario_neto_check
            }
        }
        El campo balance.neto_real debe = total - refunds - credit_notes.
        """
        conn = self.db.conn

        venta = conn.execute("SELECT * FROM ventas WHERE id = ?", (sale_id,)).fetchone()
        if not venta:
            raise VentaNoEncontradaError(f"VENTA_NO_ENCONTRADA: id={sale_id}")

        venta = dict(venta)

        items = [dict(r) for r in conn.execute(
            "SELECT * FROM detalles_venta WHERE venta_id = ?", (sale_id,)
        ).fetchall()]

        payments = [dict(r) for r in conn.execute(
            "SELECT * FROM payments WHERE venta_id = ?", (sale_id,)
        ).fetchall()]

        inv_movs = [dict(r) for r in conn.execute(
            "SELECT * FROM inventory_movements WHERE reference_id = ? AND reference_type LIKE 'VENTA%'",
            (sale_id,)
        ).fetchall()]

        caja_movs = [dict(r) for r in conn.execute(
            "SELECT * FROM movimientos_caja WHERE venta_id = ?", (sale_id,)
        ).fetchall()]

        refunds = [dict(r) for r in conn.execute(
            "SELECT * FROM sale_refunds WHERE sale_id = ?", (sale_id,)
        ).fetchall()]

        notas = [dict(r) for r in conn.execute(
            "SELECT * FROM credit_notes WHERE sale_id = ?", (sale_id,)
        ).fetchall()]

        total_original = float(venta["total"])
        total_refunds = sum(float(r["amount"]) for r in refunds)
        total_notas = sum(float(n["amount"]) for n in notas)
        neto_real = total_original - total_refunds - total_notas

        # Verificación de inventario: suma de movimientos debe cuadrar
        inv_neto = sum(float(m["quantity"]) for m in inv_movs)

        return {
            "venta":               venta,
            "items":               items,
            "payments":            payments,
            "inventory_movements": inv_movs,
            "caja_movements":      caja_movs,
            "refunds":             refunds,
            "credit_notes":        notas,
            "balance": {
                "total_original":       total_original,
                "total_refunds":        total_refunds,
                "total_credit_notes":   total_notas,
                "neto_real":            round(neto_real, 4),
                "inventario_movs_neto": round(inv_neto, 4),
            },
        }

    # ── Eventos post-commit ───────────────────────────────────────────────────

    def _fire_event(self, tipo: str, payload: dict) -> None:
        try:
            from core.events.event_bus import get_bus
            get_bus().publish(tipo, payload, async_=True)
        except Exception as e:
            logger.warning("EventBus %s falló (no crítico): %s", tipo, e)
