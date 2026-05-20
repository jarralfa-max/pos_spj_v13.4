# core/repositories/whatsapp_metrics_repository.py
"""Métricas WhatsApp desde pedidos_whatsapp y bot_sessions."""
from __future__ import annotations
import logging
from typing import Dict

logger = logging.getLogger("spj.repo.wa_metrics")


class WhatsAppMetricsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_metrics(self) -> Dict:
        m: Dict = {
            "total_pedidos": 0, "pedidos_hoy": 0,
            "pendientes": 0, "valor_total": 0.0,
            "sesiones_activas": 0,
        }
        queries = [
            ("SELECT COUNT(*) FROM pedidos_whatsapp",                           "total_pedidos"),
            ("SELECT COUNT(*) FROM pedidos_whatsapp WHERE DATE(fecha)=DATE('now')", "pedidos_hoy"),
            ("SELECT COUNT(*) FROM pedidos_whatsapp WHERE estado='pendiente'",  "pendientes"),
            ("SELECT COALESCE(SUM(total),0) FROM pedidos_whatsapp "
             "WHERE estado NOT IN ('cancelado','rechazado')",                    "valor_total"),
            ("SELECT COUNT(*) FROM bot_sessions",                               "sesiones_activas"),
        ]
        for sql, key in queries:
            try:
                val = self.conn.execute(sql).fetchone()[0]
                m[key] = float(val) if key == "valor_total" else int(val)
            except Exception as e:
                logger.debug("metrics query [%s]: %s", key, e)
        return m
