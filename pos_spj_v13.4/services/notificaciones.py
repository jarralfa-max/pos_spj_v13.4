
# services/notificaciones.py — SPJ POS v11
"""
Sistema de notificaciones del POS.
  - Alerta sonora cuando llega pedido por WhatsApp
  - Popup visual con datos del pedido
  - Cola de pedidos pendientes en tiempo real
  - Notificaciones de pago confirmado
"""
from __future__ import annotations
import logging, threading, time
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger("spj.notificaciones")


# SonidoAlerta movido a ui/sonido_alerta.py (módulo dedicado)
try:
    from ui.sonido_alerta import SonidoAlerta
except ImportError:
    class SonidoAlerta:
        @staticmethod
        def play_alert(): print("\a",end="",flush=True)
        @staticmethod
        def play_pago(): print("\a",end="",flush=True)
        @staticmethod
        def play_error(): print("\a",end="",flush=True)


class GestorNotificaciones(QObject):
    """
    Monitorea la BD en busca de pedidos nuevos y emite señales PyQt5.
    Se ejecuta con un QTimer en el hilo principal.
    """
    pedido_nuevo      = pyqtSignal(dict)   # pedido recibido por WA
    pago_confirmado   = pyqtSignal(dict)   # pago aprobado MP
    alerta_stock      = pyqtSignal(str)    # mensaje de stock bajo
    alerta_lote       = pyqtSignal(str)    # lote por caducar

    def __init__(self, conn, intervalo_ms: int = 5000, parent=None):
        super().__init__(parent)
        self.conn         = conn
        self._timer       = QTimer(self)
        self._timer.setInterval(intervalo_ms)
        self._timer.timeout.connect(self._check)
        self._last_pedido = self._get_last_pedido_id()
        self._last_pago   = self._get_last_pago_id()

    def iniciar(self):
        self._timer.start()
        logger.debug("Gestor notificaciones iniciado")

    def detener(self):
        self._timer.stop()

    def _check(self):
        try:
            self._check_pedidos_wa()
            self._check_pagos()
        except Exception as e:
            logger.debug("notificaciones check: %s", e)

    def _check_pedidos_wa(self):
        rows = self.conn.execute("""
            SELECT id, numero_whatsapp, cliente_nombre, total, estado, fecha
            FROM pedidos_whatsapp
            WHERE id > ? AND leido=0
            ORDER BY id""",
            (self._last_pedido,)).fetchall()
        for row in rows:
            pedido = dict(row)
            self._last_pedido = pedido["id"]
            self.conn.execute(
                "UPDATE pedidos_whatsapp SET leido=1 WHERE id=?", (pedido["id"],))
            try: self.conn.commit()
            except Exception: pass
            SonidoAlerta.play_alert()
            self.pedido_nuevo.emit(pedido)
            logger.info("Pedido WA nuevo: #%d %s $%.2f",
                        pedido["id"], pedido["cliente_nombre"],
                        float(pedido.get("total", 0)))

    def _check_pagos(self):
        rows = self.conn.execute("""
            SELECT p.id, p.cliente_nombre, p.total, l.payment_id
            FROM pedidos_whatsapp p
            JOIN links_pago l ON l.pedido_id=p.id
            WHERE l.id > ? AND l.estado='pagado'
            ORDER BY l.id""",
            (self._last_pago,)).fetchall()
        for row in rows:
            pago = dict(row)
            self._last_pago = pago["id"]
            SonidoAlerta.play_pago()
            self.pago_confirmado.emit(pago)

    def _get_last_pedido_id(self) -> int:
        try:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(id),0) FROM pedidos_whatsapp").fetchone()
            return row[0] or 0
        except Exception:
            return 0

    def _get_last_pago_id(self) -> int:
        try:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(id),0) FROM links_pago WHERE estado='pagado'").fetchone()
            return row[0] or 0
        except Exception:
            return 0
