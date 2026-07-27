# core/repositories/whatsapp_metrics_repository.py
"""Métricas del módulo WhatsApp.

El módulo desktop debe mostrar KPIs desde las fuentes reales del sistema actual:
- Pedidos/valor: tabla `ventas` con canal/source_channel WhatsApp.
- Mensajes: `message_log` del microservicio si existe, con fallback a tablas legacy.
- Cola: `wa_message_queue` cuando exista.
- Sesiones: `conversations` del microservicio si existe, con fallback a bot_sessions.

Las tablas legacy se conservan como fallback, pero ya no son la fuente primaria.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("spj.repo.wa_metrics")


class WhatsAppMetricsRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_metrics(self) -> Dict[str, Any]:
        metrics: Dict[str, Any] = {
            "mensajes_hoy": 0,
            "total_mensajes": 0,
            "total_pedidos": 0,
            "pedidos_hoy": 0,
            "pendientes": 0,
            "cola_pendiente": 0,
            "valor_total": 0.0,
            "sesiones_activas": 0,
            "metrics_source": "runtime+legacy",
        }

        metrics.update(self._sales_metrics())
        metrics.update(self._queue_metrics())
        metrics.update(self._context_db_metrics())
        self._legacy_fill(metrics)
        return metrics

    # ── Pedidos / valor generado ──────────────────────────────────────────────
    def _sales_metrics(self) -> Dict[str, Any]:
        where = """
            WHERE LOWER(COALESCE(canal, '')) = 'whatsapp'
               OR LOWER(COALESCE(source_channel, '')) = 'whatsapp'
               OR LOWER(COALESCE(estado, '')) = 'pendiente_wa'
               OR UPPER(COALESCE(folio, '')) LIKE 'WA-%'
        """
        return {
            "total_pedidos": self._scalar(f"SELECT COUNT(*) FROM ventas {where}", 0),
            "pedidos_hoy": self._scalar(f"SELECT COUNT(*) FROM ventas {where} AND DATE(fecha)=DATE('now')", 0),
            "pendientes": self._scalar(
                f"SELECT COUNT(*) FROM ventas {where} "
                "AND LOWER(COALESCE(estado,'')) IN ('pendiente_wa','pendiente','programado','confirmado')",
                0,
            ),
            "valor_total": float(self._scalar(
                f"SELECT COALESCE(SUM(total),0) FROM ventas {where} "
                "AND LOWER(COALESCE(estado,'')) NOT IN ('cancelado','rechazado')",
                0.0,
            ) or 0.0),
        }

    # ── Cola de salida legacy/canónica ────────────────────────────────────────
    def _queue_metrics(self) -> Dict[str, Any]:
        return {
            "cola_pendiente": self._scalar(
                "SELECT COUNT(*) FROM wa_message_queue "
                "WHERE LOWER(COALESCE(status,'')) IN ('pending','pendiente','queued','retry')",
                0,
            )
        }

    # ── Métricas del microservicio ────────────────────────────────────────────
    def _context_db_metrics(self) -> Dict[str, Any]:
        db_path = self._context_db_path()
        if not db_path or not db_path.exists():
            return {}
        try:
            ctx = sqlite3.connect(str(db_path))
            try:
                return {
                    "mensajes_hoy": self._scalar_ctx(
                        ctx,
                        "SELECT COUNT(*) FROM message_log WHERE DATE(timestamp)=DATE('now')",
                        0,
                    ),
                    "total_mensajes": self._scalar_ctx(
                        ctx,
                        "SELECT COUNT(*) FROM message_log",
                        0,
                    ),
                    "sesiones_activas": self._scalar_ctx(
                        ctx,
                        "SELECT COUNT(*) FROM conversations "
                        "WHERE datetime(last_activity) >= datetime('now','-30 minutes')",
                        0,
                    ),
                }
            finally:
                ctx.close()
        except Exception as exc:
            logger.debug("context db metrics unavailable: %s", exc)
            return {}

    def _context_db_path(self) -> Path | None:
        env_path = os.getenv("CONTEXT_DB_PATH")
        if env_path:
            return Path(env_path)
        try:
            repo_root = Path(__file__).resolve().parents[3]
            return repo_root / "whatsapp_service" / "data" / "conversations.db"
        except Exception:
            return None

    # ── Legacy fallback ───────────────────────────────────────────────────────
    def _legacy_fill(self, metrics: Dict[str, Any]) -> None:
        if not metrics.get("total_pedidos"):
            metrics["total_pedidos"] = self._scalar("SELECT COUNT(*) FROM pedidos_whatsapp", 0)
        if not metrics.get("pedidos_hoy"):
            metrics["pedidos_hoy"] = self._scalar(
                "SELECT COUNT(*) FROM pedidos_whatsapp WHERE DATE(fecha)=DATE('now')", 0
            )
        if not metrics.get("pendientes"):
            metrics["pendientes"] = self._scalar(
                "SELECT COUNT(*) FROM pedidos_whatsapp WHERE estado='pendiente'", 0
            )
        if not metrics.get("valor_total"):
            metrics["valor_total"] = float(self._scalar(
                "SELECT COALESCE(SUM(total),0) FROM pedidos_whatsapp "
                "WHERE estado NOT IN ('cancelado','rechazado')", 0.0
            ) or 0.0)
        if not metrics.get("sesiones_activas"):
            metrics["sesiones_activas"] = self._scalar("SELECT COUNT(*) FROM bot_sessions", 0)
        if not metrics.get("total_mensajes"):
            total = self._scalar("SELECT COUNT(*) FROM bot_mensajes_log", 0)
            if not total:
                total = self._scalar("SELECT COUNT(*) FROM wa_message_queue", 0)
            metrics["total_mensajes"] = total
        if not metrics.get("mensajes_hoy"):
            hoy = self._scalar("SELECT COUNT(*) FROM bot_mensajes_log WHERE DATE(fecha)=DATE('now')", 0)
            if not hoy:
                hoy = self._scalar("SELECT COUNT(*) FROM wa_message_queue WHERE DATE(fecha_creacion)=DATE('now')", 0)
            metrics["mensajes_hoy"] = hoy

    # ── Helpers seguros ───────────────────────────────────────────────────────
    def _scalar(self, sql: str, default: Any) -> Any:
        try:
            row = self.conn.execute(sql).fetchone()
            return row[0] if row else default
        except Exception as exc:
            logger.debug("metrics query failed: %s | %s", sql.split()[1:4], exc)
            return default

    def _scalar_ctx(self, ctx_conn, sql: str, default: Any) -> Any:
        try:
            row = ctx_conn.execute(sql).fetchone()
            return row[0] if row else default
        except Exception as exc:
            logger.debug("context metrics query failed: %s", exc)
            return default
