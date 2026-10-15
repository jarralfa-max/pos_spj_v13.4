from __future__ import annotations
from decimal import Decimal
from whatsapp_service.domain.money import to_decimal
import hashlib
from backend.shared.ids import new_uuid


class AIIntentAuditLog:
    def __init__(self, db):
        self.db = db

    def write(self, *, phone: str, message: str, intent: str, confidence: Decimal, source: str,
              fallback_reason: str = "", needs_clarification: bool = False, latency_ms: int = 0,
              model: str = "", error: str = ""):
        try:
            ph = hashlib.sha256((phone or "").encode("utf-8")).hexdigest()[:16]
            preview = (message or "")[:160]
            self.db.execute(
                """
                INSERT INTO ai_intent_log(id,phone_hash,message_preview,intent,confidence,source,fallback_reason,
                                          needs_clarification,latency_ms,model,error)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (new_uuid(), ph, preview, intent, to_decimal(confidence or 0), source, fallback_reason,
                 1 if needs_clarification else 0, int(latency_ms or 0), model, (error or "")[:200])
            )
            self.db.commit()
        except Exception:
            pass

