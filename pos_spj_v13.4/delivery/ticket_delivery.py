
# delivery/ticket_delivery.py — SPJ POS v11
"""
Generación de tickets de delivery.
Ticket cliente: resumen + QR de seguimiento/mapa.
Ticket repartidor: dirección + QR mapa + estado pago.
"""
from __future__ import annotations
import logging
from datetime import datetime
from core.db.connection import get_connection

logger = logging.getLogger("spj.delivery.ticket")

GOOGLE_MAPS_BASE = "https://maps.google.com/?q="


class TicketDelivery:
    def __init__(self, conn=None):
        self.conn = conn or get_connection()

    def generar_ticket_cliente(self, pedido_id: int) -> dict:
        pedido = self._get_pedido(pedido_id)
        if not pedido:
            return {}
        items  = self._get_items(pedido_id)
        qr_mapa = self._url_mapa(pedido.get("direccion_entrega",""))
        return {
            "tipo":       "cliente",
            "pedido_id":  pedido_id,
            "folio":      f"DEL-{pedido_id:06d}",
            "sucursal":   pedido.get("sucursal_nombre", "Principal"),
            "cliente":    pedido.get("cliente_nombre","—"),
            "telefono":   pedido.get("numero_whatsapp",""),
            "direccion":  pedido.get("direccion_entrega","Recoger en mostrador"),
            "items":      items,
            "subtotal":   float(pedido.get("subtotal",0)),
            "total":      float(pedido.get("total",0)),
            "forma_pago": pedido.get("forma_pago","efectivo"),
            "pago_confirmado": bool(pedido.get("pago_confirmado")),
            "qr_mapa_url": qr_mapa,
            "fecha":      datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

    def generar_ticket_repartidor(self, pedido_id: int) -> dict:
        pedido = self._get_pedido(pedido_id)
        if not pedido:
            return {}
        items  = self._get_items(pedido_id)
        qr_mapa = self._url_mapa(pedido.get("direccion_entrega",""))
        rep_id  = pedido.get("repartidor_id")
        rep_nombre = "Sin asignar"
        if rep_id:
            row = self.conn.execute(
                "SELECT nombre FROM drivers WHERE id=?", (rep_id,)).fetchone()
            if row: rep_nombre = row[0]
        return {
            "tipo":            "repartidor",
            "pedido_id":       pedido_id,
            "folio":           f"DEL-{pedido_id:06d}",
            "repartidor":      rep_nombre,
            "cliente":         pedido.get("cliente_nombre","—"),
            "telefono_cliente":pedido.get("numero_whatsapp",""),
            "direccion":       pedido.get("direccion_entrega","—"),
            "items":           items,
            "total":           float(pedido.get("total",0)),
            "forma_pago":      pedido.get("forma_pago","efectivo"),
            "pago_confirmado": bool(pedido.get("pago_confirmado")),
            "cobrar_en_puerta":not bool(pedido.get("pago_confirmado")) and pedido.get("forma_pago") in ("efectivo","tarjeta"),
            "qr_mapa_url":     qr_mapa,
            "notas":           pedido.get("notas",""),
            "fecha":           datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

    def imprimir_tickets(self, pedido_id: int, impresora=None) -> bool:
        """Imprime ambos tickets (cliente + repartidor)."""
        tc = self.generar_ticket_cliente(pedido_id)
        tr = self.generar_ticket_repartidor(pedido_id)
        if not tc or not tr:
            return False
        for ticket in (tc, tr):
            texto = self._formato_escpos(ticket)
            if impresora:
                try:
                    impresora._raw(texto.encode("utf-8", errors="replace"))
                except Exception as e:
                    logger.error("imprimir ticket: %s", e)
            else:
                logger.info("TICKET [%s]:\n%s", ticket["tipo"], texto)
        return True

    def _formato_escpos(self, ticket: dict) -> str:
        ESC = "\x1b"
        BOLD_ON  = ESC + "E\x01"
        BOLD_OFF = ESC + "E\x00"
        CENTER   = ESC + "a\x01"
        LEFT     = ESC + "a\x00"
        CUT      = ESC + "i"

        lines = [
            CENTER + BOLD_ON + "SPJ POLLOS Y CARNES" + BOLD_OFF + "\n",
            CENTER + f"Ticket {ticket['tipo'].upper()}\n",
            CENTER + f"Folio: {ticket['folio']}\n",
            CENTER + ticket.get("fecha","") + "\n",
            "-" * 32 + "\n",
            LEFT + f"Cliente: {ticket.get('cliente','')}\n",
        ]
        if ticket.get("direccion"):
            lines.append(f"Dir: {ticket['direccion']}\n")
        if ticket.get("repartidor"):
            lines.append(f"Repartidor: {ticket['repartidor']}\n")
        lines.append("-" * 32 + "\n")
        for item in ticket.get("items", []):
            lines.append(
                f"{item.get('nombre_producto','')[:20]:<20} "
                f"{float(item.get('cantidad_pesada') or item.get('cantidad_pedida',0)):.2f}kg "
                f"${float(item.get('subtotal',0)):.2f}\n")
        lines += [
            "-" * 32 + "\n",
            BOLD_ON + f"{'TOTAL':>20} ${ticket.get('total',0):.2f}" + BOLD_OFF + "\n",
            f"Pago: {ticket.get('forma_pago','').upper()}\n",
        ]
        if ticket.get("cobrar_en_puerta"):
            lines.append(BOLD_ON + "*** COBRAR EN PUERTA ***\n" + BOLD_OFF)
        if ticket.get("pago_confirmado"):
            lines.append("✓ PAGADO\n")
        if ticket.get("qr_mapa_url"):
            # Intentar imprimir QR del mapa via ESC/POS
            try:
                from delivery.mapas_qr import MapasQR
                qr_cmds = MapasQR().escpos_qr_mapa(
                    direccion=ticket.get("direccion"),
                )
                if qr_cmds:
                    lines.append("\nMapa:")
                    # Insertar bytes crudos ESC/POS del QR
                    lines.append(f"__ESCPOS_RAW__{qr_cmds.hex()}__END__")
                else:
                    lines.append(f"\nMapa: {ticket['qr_mapa_url']}\n")
            except Exception:
                lines.append(f"\nMapa: {ticket['qr_mapa_url']}\n")
        lines.append("\n\n" + CUT)
        return "".join(lines)

    def _get_pedido(self, pedido_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM pedidos_whatsapp WHERE id=?", (pedido_id,)).fetchone()
        return dict(row) if row else None

    def _get_items(self, pedido_id: int) -> list:
        rows = self.conn.execute(
            "SELECT * FROM pedidos_whatsapp_items WHERE pedido_id=?",
            (pedido_id,)).fetchall()
        return [dict(r) for r in rows]

    def _url_mapa(self, direccion: str) -> str:
        if not direccion:
            return ""
        from urllib.parse import quote
        return GOOGLE_MAPS_BASE + quote(direccion)
