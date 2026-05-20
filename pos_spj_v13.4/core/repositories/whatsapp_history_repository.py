# core/repositories/whatsapp_history_repository.py
"""Acceso de solo lectura al historial de mensajes WhatsApp."""
from __future__ import annotations
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("spj.repo.whatsapp_history")

# Orden de prioridad de tablas a consultar
_QUERIES = [
    (
        "wa_message_queue",
        """SELECT fecha_creacion, to_number,
                  CASE WHEN status='sent' THEN '⬆️ Salida' ELSE '⏳ Cola' END,
                  COALESCE(message,''), COALESCE(status,'pendiente')
           FROM wa_message_queue
           WHERE (? = '' OR to_number LIKE ? OR message LIKE ?)
           ORDER BY fecha_creacion DESC LIMIT 200""",
    ),
    (
        "bot_mensajes_log",
        """SELECT fecha, numero_whatsapp,
                  CASE WHEN direction='in' THEN '⬇️ Entrada' ELSE '⬆️ Salida' END,
                  COALESCE(mensaje,''), COALESCE(estado,'enviado')
           FROM bot_mensajes_log
           WHERE (? = '' OR numero_whatsapp LIKE ? OR mensaje LIKE ?)
           ORDER BY fecha DESC LIMIT 200""",
    ),
    (
        "pedidos_whatsapp",
        """SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'),
                  '⬇️ Entrada', COALESCE(mensaje,''), 'recibido'
           FROM pedidos_whatsapp
           WHERE (? = '' OR numero_whatsapp LIKE ? OR telefono_cliente LIKE ?)
           ORDER BY fecha DESC LIMIT 100""",
    ),
]

# Separate query for pedidos_whatsapp when searching by message text
_PEDIDOS_MENSAJE_QUERY = """
    SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'),
           '⬇️ Entrada', COALESCE(mensaje,''), 'recibido'
    FROM pedidos_whatsapp
    WHERE ? != '' AND COALESCE(mensaje,'') LIKE ?
    ORDER BY fecha DESC LIMIT 100
"""


class WhatsAppHistoryRepository:
    """Lee historial de mensajes con parámetros SQL seguros (sin interpolación)."""

    def __init__(self, db):
        self._db = db

    def get_history(self, buscar: str = "") -> List[Tuple]:
        """
        Retorna filas del historial. Usa parámetros seguros.
        Prueba tablas en orden de prioridad; devuelve la primera con datos.
        """
        like_param = f"%{buscar}%" if buscar else ""
        results: List[Tuple] = []
        for table_name, query in _QUERIES:
            try:
                rows = self._db.execute(
                    query, (buscar, like_param, like_param)
                ).fetchall()
                results.extend(tuple(r) for r in rows)
                if results:
                    return results
            except Exception as e:
                logger.debug("history query %s: %s", table_name, e)
        # Fallback: search pedidos_whatsapp by mensaje text
        if buscar and not results:
            try:
                rows = self._db.execute(
                    _PEDIDOS_MENSAJE_QUERY, (buscar, like_param)
                ).fetchall()
                results.extend(tuple(r) for r in rows)
            except Exception as e:
                logger.debug("history query pedidos_mensaje: %s", e)
        return results
