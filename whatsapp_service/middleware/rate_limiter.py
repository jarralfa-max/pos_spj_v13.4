# middleware/rate_limiter.py — Anti-spam y rate limiting
"""
Limita mensajes por teléfono por minuto.
Filtra mensajes de grupos y vacíos.
"""
from __future__ import annotations
import time
import logging
from collections import defaultdict
from config.settings import MAX_MESSAGES_PER_MINUTE

logger = logging.getLogger("wa.ratelimit")


class RateLimiter:
    def __init__(self, max_per_minute: int = MAX_MESSAGES_PER_MINUTE):
        self.max_per_minute = max_per_minute
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, phone: str) -> bool:
        """Retorna True si el teléfono puede enviar otro mensaje."""
        now = time.time()
        window = now - 60

        # Limpiar timestamps viejos
        self._timestamps[phone] = [
            t for t in self._timestamps[phone] if t > window
        ]

        if len(self._timestamps[phone]) >= self.max_per_minute:
            logger.warning("Rate limit hit: %s (%d msgs/min)",
                           phone, len(self._timestamps[phone]))
            return False

        self._timestamps[phone].append(now)
        return True

    @staticmethod
    def is_group_message(data: dict) -> bool:
        """Detecta si el mensaje viene de un grupo (no procesamos grupos)."""
        try:
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            if messages:
                msg = messages[0]
                # Grupos tienen "from" con formato diferente
                if msg.get("from", "").endswith("@g.us"):
                    return True
                # O tienen context.group_id
                if msg.get("context", {}).get("group_id"):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def is_status_update(data: dict) -> bool:
        """Detecta si es un status update (read receipts, etc.) — no un mensaje."""
        try:
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            return "statuses" in value and "messages" not in value
        except Exception:
            return False
