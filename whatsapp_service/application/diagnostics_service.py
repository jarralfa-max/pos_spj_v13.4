# application/diagnostics_service.py — WA-20 (§58 del prompt maestro, observabilidad)
"""
DiagnosticsService — métricas NUMÉRICAS de operación del canal,
complementando `/health` (WA-4, HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN por
subsistema — una señal booleana-ish para alertar, no para diagnosticar).
`/diagnostics` responde "cuántas conversaciones hay en cada estado,
cuántos mensajes hoy, qué tan atrasada está la cola" — la pregunta que un
operador hace DESPUÉS de que `/health` ya dijo DEGRADED.

Todas las consultas leen la MISMA conexión que el resto del
`CompositionRoot` — sin una BD de métricas separada. Ninguna métrica
aquí requiere que el canal esté wireado al webhook en vivo: todas
devuelven honestamente 0/vacío mientras no haya tráfico real, igual que
cada mecanismo nuevo desde WA-4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(oldest_iso: Optional[str]) -> Optional[float]:
    if not oldest_iso:
        return None
    try:
        oldest = datetime.fromisoformat(oldest_iso)
    except (TypeError, ValueError):
        return None
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - oldest).total_seconds()


class DiagnosticsService:
    def __init__(self, root) -> None:
        self._root = root

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "generated_at": _utcnow_iso(),
            "conversations": self._conversations(),
            "messages": self._messages(),
            "inbox": self._queue_summary("whatsapp_inbox", pending_statuses=("PENDING", "RETRY")),
            "outbox": self._queue_summary("whatsapp_outbox", pending_statuses=("PENDING",)),
            "dead_letter": self._dead_letter(),
            "handoff": self._handoff(),
            "idempotency": self._idempotency(),
            "delivery_requests": self._by_status("whatsapp_delivery_requests"),
            "order_drafts": self._by_status("whatsapp_order_drafts"),
            "quote_drafts": self._by_status("whatsapp_quote_drafts"),
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _conn(self):
        return self._root.registry.get("whatsapp_db_connection")

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        try:
            row = self._conn().execute(sql, params).fetchone()
            return row[0] if row and row[0] is not None else default
        except Exception:
            return default

    def _by_status(self, table: str) -> Dict[str, int]:
        try:
            rows = self._conn().execute(
                f"SELECT status, COUNT(*) FROM {table} GROUP BY status"
            ).fetchall()
        except Exception:
            return {}
        return {status: count for status, count in rows}

    # ── Secciones ────────────────────────────────────────────────────────────

    def _conversations(self) -> Dict[str, Any]:
        return {
            "by_state": self._by_status_column("whatsapp_conversations", "state"),
            "total": self._scalar("SELECT COUNT(*) FROM whatsapp_conversations"),
        }

    def _by_status_column(self, table: str, column: str) -> Dict[str, int]:
        try:
            rows = self._conn().execute(
                f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}"
            ).fetchall()
        except Exception:
            return {}
        return {value: count for value, count in rows}

    def _messages(self) -> Dict[str, Any]:
        return {
            "total": self._scalar("SELECT COUNT(*) FROM whatsapp_messages"),
            "today": self._scalar(
                "SELECT COUNT(*) FROM whatsapp_messages WHERE DATE(created_at)=DATE('now')"
            ),
            "by_direction": self._by_status_column("whatsapp_messages", "direction"),
        }

    def _queue_summary(self, table: str, *, pending_statuses: tuple) -> Dict[str, Any]:
        placeholders = ",".join("?" for _ in pending_statuses)
        pending = self._scalar(
            f"SELECT COUNT(*) FROM {table} WHERE status IN ({placeholders})", pending_statuses,
        )
        oldest = self._scalar(
            f"SELECT MIN(created_at) FROM {table} WHERE status IN ({placeholders})",
            pending_statuses, default=None,
        )
        return {"pending": pending, "oldest_pending_age_seconds": _age_seconds(oldest)}

    def _dead_letter(self) -> Dict[str, Any]:
        return {
            "unresolved": self._scalar("SELECT COUNT(*) FROM whatsapp_dead_letter WHERE resolved_at IS NULL"),
            "total": self._scalar("SELECT COUNT(*) FROM whatsapp_dead_letter"),
        }

    def _handoff(self) -> Dict[str, Any]:
        oldest = self._scalar(
            "SELECT MIN(created_at) FROM whatsapp_handoff_requests WHERE status IN ('OPEN','ASSIGNED')",
            default=None,
        )
        return {
            "by_status": self._by_status("whatsapp_handoff_requests"),
            "oldest_open_age_seconds": _age_seconds(oldest),
        }

    def _idempotency(self) -> Dict[str, Any]:
        return {
            "by_status": self._by_status("whatsapp_business_operation_idempotency"),
            "by_operation_type": self._by_status_column(
                "whatsapp_business_operation_idempotency", "operation_type"
            ),
        }
