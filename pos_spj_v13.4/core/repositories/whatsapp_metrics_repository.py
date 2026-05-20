# core/repositories/whatsapp_metrics_repository.py
"""Métricas de pedidos y actividad WhatsApp."""
from __future__ import annotations
import logging
from typing import Dict

logger = logging.getLogger("spj.repo.whatsapp_metrics")


class WhatsAppMetricsRepository:
    """Consultas de métricas agregadas para el módulo WhatsApp."""

    def __init__(self, db):
        self._db = db

    def get_metrics(self) -> Dict:
        try:
            row = self._db.execute("""
                SELECT
                    COUNT(*),
                    COUNT(CASE WHEN DATE(fecha)=DATE('now') THEN 1 END),
                    COUNT(CASE WHEN estado='pendiente' THEN 1 END),
                    COALESCE(SUM(CASE WHEN estado NOT IN ('cancelado','rechazado')
                                      THEN total END), 0)
                FROM pedidos_whatsapp
            """).fetchone()
            tot, hoy, pend, total_v = (row or (0, 0, 0, 0.0))
        except Exception as e:
            logger.debug("get_metrics pedidos: %s", e)
            tot = hoy = pend = 0
            total_v = 0.0
        sesiones = self._scalar("SELECT COUNT(*) FROM bot_sessions", 0)
        return {
            "total": int(tot),
            "hoy": int(hoy),
            "pendientes": int(pend),
            "valor_total": float(total_v),
            "sesiones": sesiones,
        }

    def _scalar(self, query: str, default):
        try:
            row = self._db.execute(query).fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.debug("metrics scalar: %s — %s", query[:50], e)
            return default
