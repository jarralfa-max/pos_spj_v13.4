from __future__ import annotations
import json
import os
import asyncio
from dataclasses import dataclass
from typing import Optional

try:
    from whatsapp_service.ai.intent_schema import AIIntentResult
except Exception:  # pragma: no cover
    from ai.intent_schema import AIIntentResult


@dataclass
class AIClientResponse:
    ok: bool
    result: Optional[AIIntentResult] = None
    error: str = ""
    latency_ms: int = 0


class CloudIntentAIClient:
    def __init__(self, db=None):
        self.db = db

    def _cfg(self, key: str, default: str = "") -> str:
        env_map = {
            "ai_intent_enabled": "AI_INTENT_ENABLED",
            "ai_provider": "AI_PROVIDER",
            "ai_model": "AI_MODEL",
            "ai_api_key": "AI_API_KEY",
            "ai_timeout_seconds": "AI_TIMEOUT_SECONDS",
        }
        val = ""
        if self.db is not None:
            try:
                row = self.db.execute("SELECT valor FROM configuraciones WHERE clave=? LIMIT 1", (key,)).fetchone()
                val = str(row[0]) if row and row[0] is not None else ""
            except Exception:
                val = ""
        return val or os.getenv(env_map.get(key, ""), default)

    async def parse(self, context: dict) -> AIClientResponse:
        timeout_s = float(self._cfg("ai_timeout_seconds", "4") or "4")
        provider = (self._cfg("ai_provider", "mock") or "mock").lower()
        model = self._cfg("ai_model", "mock-intent-v1")
        api_key = self._cfg("ai_api_key", "")
        if provider != "mock" and not api_key:
            return AIClientResponse(ok=False, error="missing_api_key")
        try:
            await asyncio.wait_for(asyncio.sleep(0.01), timeout=timeout_s)
            # mock/fake first phase: deterministic safe response
            text = str(context.get("message") or "").lower()
            payload = {"intent": "unknown", "confidence": 0.1, "products": []}
            if "cotiz" in text:
                payload.update({"intent": "create_quote", "confidence": 0.87})
            elif "acepto" in text and "ajuste" in text:
                payload.update({"intent": "accept_adjustment", "confidence": 0.95})
            elif "rechazo" in text and "ajuste" in text:
                payload.update({"intent": "reject_adjustment", "confidence": 0.95})
            elif "quiero" in text:
                payload.update({"intent": "create_order", "confidence": 0.86})
            _ = model  # keep model configurable for future provider
            return AIClientResponse(ok=True, result=AIIntentResult.model_validate(json.loads(json.dumps(payload))))
        except Exception as exc:
            err = str(exc).strip() or exc.__class__.__name__
            return AIClientResponse(ok=False, error=err)
