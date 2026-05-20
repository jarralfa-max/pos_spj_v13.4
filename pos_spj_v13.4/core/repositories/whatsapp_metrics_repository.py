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
        tot = self._scalar("SELECT COUNT(*) FROM pedidos_whatsapp", 0)
        hoy = self._scalar(
            "SELECT COUNT(*) FROM pedidos_whatsapp WHERE DATE(fecha)=DATE('now')", 0)
        pend = self._scalar(
            "SELECT COUNT(*) FROM pedidos_whatsapp WHERE estado='pendiente'", 0)
        total_v = self._scalar(
            "SELECT COALESCE(SUM(total),0) FROM pedidos_whatsapp "
            "WHERE estado NOT IN ('cancelado','rechazado')", 0.0)
        sesiones = self._scalar("SELECT COUNT(*) FROM bot_sessions", 0)
        return {
            "total": tot,
            "hoy": hoy,
            "pendientes": pend,
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
