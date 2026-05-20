# core/repositories/whatsapp_history_repository.py
"""Historial unificado de mensajes WhatsApp. Abstrae múltiples tablas legacy."""
from __future__ import annotations
import logging
from typing import List, Dict

logger = logging.getLogger("spj.repo.wa_history")


class WhatsAppHistoryRepository:
    """
    Fuente canónica: wa_message_queue → bot_mensajes_log → pedidos_whatsapp.
    Usa LIKE con parámetros (sin interpolación directa) para evitar SQL injection.
    """

    def __init__(self, conn):
        self.conn = conn

    def get_history(self, search: str = "", limit: int = 200) -> List[Dict]:
        pattern = f"%{search}%" if search else None
        for query_fn in (self._query_wa_queue, self._query_bot_log,
                         self._query_pedidos_wa):
            try:
                rows = query_fn(pattern, limit)
                if rows:
                    return rows
            except Exception as e:
                logger.debug("history query failed: %s", e)
        return []

    def _query_wa_queue(self, pattern: Optional[str], limit: int) -> List[Dict]:
        if pattern:
            rows = self.conn.execute(
                "SELECT fecha_creacion, to_number, "
                "CASE WHEN status='sent' THEN '⬆️ Salida' ELSE '⏳ Cola' END, "
                "COALESCE(message,''), COALESCE(status,'pendiente') "
                "FROM wa_message_queue "
                "WHERE to_number LIKE ? OR message LIKE ? "
                "ORDER BY fecha_creacion DESC LIMIT ?",
                (pattern, pattern, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fecha_creacion, to_number, "
                "CASE WHEN status='sent' THEN '⬆️ Salida' ELSE '⏳ Cola' END, "
                "COALESCE(message,''), COALESCE(status,'pendiente') "
                "FROM wa_message_queue ORDER BY fecha_creacion DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"fecha": r[0], "numero": r[1], "direccion": r[2],
                 "mensaje": r[3], "estado": r[4]} for r in rows]

    def _query_bot_log(self, pattern: Optional[str], limit: int) -> List[Dict]:
        if pattern:
            rows = self.conn.execute(
                "SELECT fecha, numero_whatsapp, "
                "CASE WHEN direction='in' THEN '⬇️ Entrada' ELSE '⬆️ Salida' END, "
                "COALESCE(mensaje,texto,''), COALESCE(estado,'enviado') "
                "FROM bot_mensajes_log "
                "WHERE numero_whatsapp LIKE ? OR mensaje LIKE ? OR texto LIKE ? "
                "ORDER BY fecha DESC LIMIT ?",
                (pattern, pattern, pattern, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fecha, numero_whatsapp, "
                "CASE WHEN direction='in' THEN '⬇️ Entrada' ELSE '⬆️ Salida' END, "
                "COALESCE(mensaje,texto,''), COALESCE(estado,'enviado') "
                "FROM bot_mensajes_log ORDER BY fecha DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"fecha": r[0], "numero": r[1], "direccion": r[2],
                 "mensaje": r[3], "estado": r[4]} for r in rows]

    def _query_pedidos_wa(self, pattern: Optional[str], limit: int) -> List[Dict]:
        if pattern:
            rows = self.conn.execute(
                "SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'), "
                "'⬇️ Entrada', COALESCE(mensaje,''), 'recibido' "
                "FROM pedidos_whatsapp "
                "WHERE numero_whatsapp LIKE ? OR telefono_cliente LIKE ? "
                "ORDER BY fecha DESC LIMIT ?",
                (pattern, pattern, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'), "
                "'⬇️ Entrada', COALESCE(mensaje,''), 'recibido' "
                "FROM pedidos_whatsapp ORDER BY fecha DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"fecha": r[0], "numero": r[1], "direccion": r[2],
                 "mensaje": r[3], "estado": r[4]} for r in rows]


# Typing fix for Optional used inside class methods
from typing import Optional
