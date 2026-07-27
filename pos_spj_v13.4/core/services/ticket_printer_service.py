"""TicketPrinterService — generates and prints customer + driver delivery tickets.

Two ticket types:
  Customer ticket:  products, total, QR, payment method, notes, weight adjustments
  Driver ticket:    address, references, phone, payment method, total to collect, zone

Printing backend:
  - Thermal real print: PrinterService.print_ticket (ESC/POS RAW).
  - Preview mode: printable QDialog (visual only).

All heavy Qt work happens on the caller's thread (must be GUI thread).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from core.tickets.ticket_print_model import (
    TicketPrintModel, TicketItem, TicketTotals, TicketPaymentInfo, TicketBranding
)

logger = logging.getLogger("spj.services.ticket_printer")


class TicketPrinterService:
    """Generates and optionally prints delivery tickets.

    Parameters
    ----------
    db:
        SQLite connection for loading order data.
    printer_name:
        OS printer name; None = default system printer.
    preview_mode:
        True = show QDialog preview instead of printing directly.
        Useful for testing and when a physical printer is not available.
    """

    def __init__(self, db, printer_name: Optional[str] = None, preview_mode: bool = False, printer_service=None) -> None:
        self.db = db
        self._printer_name = printer_name
        self._preview_mode = preview_mode
        self._printer_service = printer_service

    # ── Public ────────────────────────────────────────────────────────────────

    def print_customer_ticket(self, order_id: int) -> bool:
        """Print the customer-facing ticket. Returns True if printed/previewed."""
        order = self._load_order(order_id)
        if not order:
            logger.warning("TicketPrinter: order %s not found", order_id)
            return False
        items  = self._load_items(order_id)
        text   = self._build_customer_ticket(order, items)
        model = self._build_customer_model(order, items)
        return self._output(text, f"Ticket Cliente #{order.get('folio') or order_id}", model=model)

    def print_driver_ticket(self, order_id: int) -> bool:
        """Print the driver-facing ticket. Returns True if printed/previewed."""
        order = self._load_order(order_id)
        if not order:
            logger.warning("TicketPrinter: order %s not found", order_id)
            return False
        text = self._build_driver_ticket(order)
        model = self._build_driver_model(order)
        return self._output(text, f"Ticket Repartidor #{order.get('folio') or order_id}", model=model)

    def print_both(self, order_id: int) -> bool:
        """Print both tickets for an order."""
        r1 = self.print_customer_ticket(order_id)
        r2 = self.print_driver_ticket(order_id)
        return r1 or r2

    # ── Ticket builders ───────────────────────────────────────────────────────

    def _build_customer_ticket(self, order: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        sep = "=" * 40
        thin = "-" * 40
        folio    = order.get("folio") or f"DEL-{order['id']}"
        nombre   = order.get("cliente_nombre") or "Cliente"
        tel      = order.get("cliente_tel") or ""
        direccion = order.get("direccion") or ""
        notas    = order.get("notas") or ""
        metodo   = order.get("pago_metodo") or "Por confirmar"
        total    = float(order.get("total") or 0)
        costo_env = float(order.get("costo_envio") or 0)
        estado   = (order.get("estado") or "").upper()
        fecha    = order.get("fecha") or ""

        lines = [
            sep,
            "        COMPROBANTE DE PEDIDO",
            sep,
            f"Folio:    {folio}",
            f"Fecha:    {fecha[:19]}",
            f"Estado:   {estado}",
            thin,
            f"Cliente:  {nombre}",
            f"Teléfono: {tel}",
            f"Dirección:",
            f"  {direccion}",
        ]
        if notas:
            lines += [f"Notas: {notas}"]
        lines += [thin, "PRODUCTOS:", thin]

        subtotal = 0.0
        for it in items:
            nombre_p = (it.get("nombre") or "Producto")[:28]
            qty = float(it.get("prepared_qty") or it.get("cantidad") or 0)
            precio = float(it.get("precio_unitario") or 0)
            sub = float(it.get("subtotal") or qty * precio)
            unidad = it.get("unidad") or "u"
            adjustment = ""
            if it.get("tolerance_exceeded"):
                req = float(it.get("cantidad") or qty)
                adjustment = f" [ajuste: {req:.3g}→{qty:.3g}{unidad}]"
            lines.append(f"  {nombre_p:<28} ${sub:>8.2f}{adjustment}")
            lines.append(f"  {qty:.3g} {unidad} x ${precio:.2f}")
            subtotal += sub

        lines += [
            thin,
            f"  {'Subtotal':<28} ${subtotal:>8.2f}",
        ]
        if costo_env > 0:
            lines.append(f"  {'Envío':<28} ${costo_env:>8.2f}")
        lines += [
            sep,
            f"  {'TOTAL':<28} ${total:>8.2f}",
            sep,
            f"Método de pago: {metodo}",
            "",
            "   Gracias por su preferencia   ",
            sep,
        ]
        return "\n".join(lines)

    def _build_driver_ticket(self, order: Dict[str, Any]) -> str:
        sep = "=" * 40
        thin = "-" * 40
        folio     = order.get("folio") or f"DEL-{order['id']}"
        nombre    = order.get("cliente_nombre") or "Cliente"
        tel       = order.get("cliente_tel") or "Sin tel."
        direccion = order.get("direccion") or "Sin dirección"
        notas     = order.get("notas") or "—"
        metodo    = order.get("pago_metodo") or "Por confirmar"
        total     = float(order.get("total") or 0)
        pago_m    = float(order.get("pago_monto") or total)
        driver    = order.get("driver_nombre") or order.get("responsable_entrega") or "N/A"
        fecha     = order.get("fecha") or ""
        tiempo    = order.get("tiempo_estimado") or 30

        cobrar_desc = "YA PAGADO" if "pagado" in metodo.lower() or "online" in metodo.lower() else f"COBRAR: ${pago_m:.2f}"

        lines = [
            sep,
            "     TICKET DE REPARTIDOR",
            sep,
            f"Folio:      {folio}",
            f"Fecha:      {fecha[:19]}",
            f"Repartidor: {driver}",
            f"SLA:        {tiempo} min",
            sep,
            "ENTREGA A:",
            thin,
            f"  {nombre}",
            f"  Tel: {tel}",
            "",
            "  DIRECCIÓN:",
            f"  {direccion}",
            "",
            f"  Notas: {notas}",
            sep,
            f"  FORMA DE COBRO: {metodo}",
            f"  {cobrar_desc}",
            sep,
            "",
            "  Firma cliente: ____________________",
            "",
            sep,
        ]
        return "\n".join(lines)

    # ── Output ────────────────────────────────────────────────────────────────

    def _output(self, text: str, title: str, model: Optional[TicketPrintModel] = None) -> bool:
        if self._preview_mode:
            return self._show_preview_dialog(text, title)
        return self._print_via_escpos(text, title, model=model)

    def _print_via_escpos(self, text: str, title: str, model: Optional[TicketPrintModel] = None) -> bool:
        if not self._printer_service or not self._printer_service.has_ticket_printer():
            logger.warning("TicketPrinter thermal print blocked (%s): no ESC/POS printer configured", title)
            return False
        try:
            payload = model.to_dict() if model else {
                "folio": title, "texto_libre": text, "items": [], "totales": {}, "plantilla": "delivery_text_ticket",
            }
            job_id = self._printer_service.print_ticket(payload)
            logger.info("TicketPrinter ESC/POS queued '%s' job_id=%s", title, job_id)
            return True
        except Exception as exc:
            logger.warning("TicketPrinter ESC/POS failed (%s): %s", title, exc)
            return False

    def _show_preview_dialog(self, text: str, title: str) -> bool:
        try:
            from PyQt5.QtWidgets import (
                QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
                QApplication,
            )
            from PyQt5.QtGui import QFont

            parent = QApplication.activeWindow()
            dlg = QDialog(parent)
            dlg.setWindowTitle(f"🖨️ {title}")
            dlg.setMinimumSize(480, 560)
            lay = QVBoxLayout(dlg)

            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setFont(QFont("Courier New", 9))
            txt.setPlainText(text)
            lay.addWidget(txt)

            btn_row = QHBoxLayout()
            btn_print = QPushButton("🖨️ Imprimir")
            btn_print.setObjectName("primaryBtn")
            btn_close = QPushButton("Cerrar")
            btn_close.setObjectName("secondaryBtn")
            btn_row.addWidget(btn_print)
            btn_row.addWidget(btn_close)
            lay.addLayout(btn_row)

            def _do_print():
                self._preview_mode = False
                self._print_via_escpos(text, title, model=None)
                self._preview_mode = True

            btn_print.clicked.connect(_do_print)
            btn_close.clicked.connect(dlg.accept)
            dlg.exec_()
            return True
        except Exception as exc:
            logger.warning("TicketPrinter preview dialog failed: %s", exc)
            return False

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = self.db.execute(
                """SELECT d.*, dr.nombre AS driver_nombre
                   FROM delivery_orders d
                   LEFT JOIN drivers dr ON dr.id = d.driver_id
                   WHERE d.id=?""",
                (order_id,),
            ).fetchone()
            return dict(row) if row else None
        except Exception as exc:
            logger.debug("TicketPrinter _load_order: %s", exc)
            return None

    def _load_items(self, order_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.db.execute(
                """SELECT nombre, cantidad, precio_unitario, subtotal, unidad,
                          prepared_qty, tolerance_exceeded
                   FROM delivery_items WHERE delivery_id=? ORDER BY id""",
                (order_id,),
            ).fetchall()
            cols = ["nombre", "cantidad", "precio_unitario", "subtotal", "unidad",
                    "prepared_qty", "tolerance_exceeded"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as exc:
            logger.debug("TicketPrinter _load_items: %s", exc)
            return []

    def _build_customer_model(self, order: Dict[str, Any], items: List[Dict[str, Any]]) -> TicketPrintModel:
        model_items = [
            TicketItem(
                nombre=str(it.get("nombre", "Producto")),
                cantidad=float(it.get("prepared_qty") or it.get("cantidad") or 0),
                precio_unitario=float(it.get("precio_unitario") or 0),
                total=float(it.get("subtotal") or 0),
                unidad=str(it.get("unidad") or "u"),
            ) for it in items
        ]
        subtotal = sum(i.total for i in model_items)
        total = float(order.get("total") or subtotal)
        return TicketPrintModel(
            ticket_type="delivery_customer",
            folio=str(order.get("folio") or f"DEL-{order.get('id','')}"),
            fecha=str(order.get("fecha") or ""),
            cajero="delivery",
            cliente_nombre=str(order.get("cliente_nombre") or "Cliente"),
            items=model_items,
            totals=TicketTotals(subtotal=subtotal, descuento=0.0, total_final=total),
            payment=TicketPaymentInfo(forma_pago=str(order.get("pago_metodo") or "")),
            branding=TicketBranding(),
            footer_message="Gracias por su preferencia",
        )

    def _build_driver_model(self, order: Dict[str, Any]) -> TicketPrintModel:
        total = float(order.get("total") or 0)
        return TicketPrintModel(
            ticket_type="delivery_driver",
            folio=str(order.get("folio") or f"DEL-{order.get('id','')}"),
            fecha=str(order.get("fecha") or ""),
            cajero=str(order.get("driver_nombre") or "driver"),
            cliente_nombre=str(order.get("cliente_nombre") or "Cliente"),
            items=[],
            totals=TicketTotals(subtotal=total, descuento=0.0, total_final=total),
            payment=TicketPaymentInfo(forma_pago=str(order.get("pago_metodo") or "")),
            branding=TicketBranding(),
            footer_message=str(order.get("direccion") or ""),
        )
