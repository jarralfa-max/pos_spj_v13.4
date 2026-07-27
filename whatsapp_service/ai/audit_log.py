from __future__ import annotations
import hashlib


class AIIntentAuditLog:
    def __init__(self, db):
        self.db = db
        self._ensure_table()

    def _ensure_table(self):
        try:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_intent_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_hash TEXT,
                    message_preview TEXT,
                    intent TEXT,
                    confidence REAL,
                    source TEXT,
                    fallback_reason TEXT,
                    needs_clarification INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT (datetime('now')),
                    latency_ms INTEGER DEFAULT 0,
                    model TEXT,
                    error TEXT
                )
                """
            )
            self.db.commit()
        except Exception:
            pass

    def write(self, *, phone: str, message: str, intent: str, confidence: float, source: str,
              fallback_reason: str = "", needs_clarification: bool = False, latency_ms: int = 0,
              model: str = "", error: str = ""):
        try:
            ph = hashlib.sha256((phone or "").encode("utf-8")).hexdigest()[:16]
            preview = (message or "")[:160]
            self.db.execute(
                """
                INSERT INTO ai_intent_log(phone_hash,message_preview,intent,confidence,source,fallback_reason,
                                          needs_clarification,latency_ms,model,error)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (ph, preview, intent, float(confidence or 0), source, fallback_reason,
                 1 if needs_clarification else 0, int(latency_ms or 0), model, (error or "")[:200])
            )
            self.db.commit()
        except Exception:
            pass

