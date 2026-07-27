from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from whatsapp_service.parser.intent_parser import IntentParser, ParsedIntent
from whatsapp_service.ai.intent_ai_client import CloudIntentAIClient
from whatsapp_service.ai.prompt_builder import build_ai_prompt_context
from whatsapp_service.ai.fallback import map_ai_to_parsed_intent
from whatsapp_service.ai.audit_log import AIIntentAuditLog
from whatsapp_service.ai.catalog_entity_extractor import CatalogEntityExtractor

logger = logging.getLogger("wa.intent_resolver")


class IntentResolver:
    def __init__(self, *, parser: IntentParser, db=None):
        self.parser = parser
        self.db = db
        self.ai_client = CloudIntentAIClient(db=db)
        self.audit = AIIntentAuditLog(db) if db is not None else None
        self.entity_extractor = CatalogEntityExtractor(parser.matcher)

    def _get_cfg(self, key: str, default: str = "") -> str:
        if self.db is not None:
            try:
                row = self.db.execute("SELECT valor FROM configuraciones WHERE clave=? LIMIT 1", (key,)).fetchone()
                if row and row[0] is not None:
                    return str(row[0])
            except Exception:
                pass
        return os.getenv(key.upper(), default)

    def _set_cfg(self, key: str, value: str) -> None:
        if self.db is None:
            return
        try:
            self.db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (key, value),
            )
            self.db.commit()
        except Exception:
            pass

    async def resolve(self, msg, ctx):
        enabled = (self._get_cfg("ai_intent_enabled", "0") or "0").lower() in ("1", "true", "yes", "on")
        min_conf = float(self._get_cfg("ai_min_confidence", "0.75") or "0.75")
        fallback_enabled = (self._get_cfg("ai_fallback_enabled", "1") or "1").lower() in ("1", "true", "yes", "on")
        if not enabled:
            self._set_cfg("ai_last_error", "IA desactivada")
            parsed = await self.parser.parse(msg)
            parsed.source = "local"
            return self._enrich_products(parsed, msg)

        ai_ctx = build_ai_prompt_context(msg.text, ctx, allowed_intents=[
            "create_order", "create_quote", "schedule_order", "change_branch",
            "accept_adjustment", "reject_adjustment", "unknown",
        ])
        ai_resp = await self.ai_client.parse(ai_ctx)
        if not ai_resp.ok or not ai_resp.result:
            self._set_cfg("ai_last_error", f"Fallback local: {ai_resp.error or 'ai_error'}")
            parsed = await self.parser.parse(msg)
            parsed.source = "local"
            parsed = self._enrich_products(parsed, msg)
            if self.audit:
                self.audit.write(phone=msg.from_number, message=msg.text, intent=parsed.intent,
                                 confidence=parsed.confidence, source="local", fallback_reason=ai_resp.error)
            return parsed

        confidence_val = getattr(ai_resp.result, "confidence", None)
        if confidence_val is None:
            self._set_cfg("ai_last_error", "Fallback local: invalid_ai_payload")
            parsed = await self.parser.parse(msg)
            parsed.source = "local"
            return self._enrich_products(parsed, msg)

        if float(confidence_val) < min_conf:
            self._set_cfg("ai_last_error", "Fallback local: low_confidence")
            parsed = await self.parser.parse(msg)
            parsed.source = "local"
            parsed = self._enrich_products(parsed, msg)
            if self.audit:
                self.audit.write(phone=msg.from_number, message=msg.text, intent=parsed.intent,
                                 confidence=parsed.confidence, source="local", fallback_reason="low_confidence")
            return parsed

        try:
            parsed = map_ai_to_parsed_intent(ai_resp.result)
        except Exception:
            self._set_cfg("ai_last_error", "Fallback local: invalid_ai_payload")
            parsed = await self.parser.parse(msg)
            parsed.source = "local"
            return self._enrich_products(parsed, msg)
        if parsed.intent == "unknown" and fallback_enabled:
            self._set_cfg("ai_last_error", "Fallback local: unknown_intent")
            parsed = await self.parser.parse(msg)
            parsed.source = "local"
        else:
            self._set_cfg("ai_last_error", "")

        parsed = self._enrich_products(parsed, msg)
        if self.audit:
            self.audit.write(phone=msg.from_number, message=msg.text, intent=parsed.intent,
                             confidence=parsed.confidence, source=getattr(parsed, "source", "ai"),
                             needs_clarification=getattr(parsed, "needs_clarification", False))
        return parsed

    def _enrich_products(self, parsed: ParsedIntent, msg) -> ParsedIntent:
        raw_text = getattr(msg, "text", "") or ""
        products: List[Dict[str, Any]] = []

        for prod in getattr(parsed, "products", []) or []:
            normalized = self.entity_extractor.normalize_product(prod)
            if normalized:
                products.append(normalized)

        if raw_text:
            try:
                local = self.parser._parse_regex(raw_text)
                for prod in getattr(local, "products", []) or []:
                    normalized = self.entity_extractor.normalize_product(prod)
                    if normalized:
                        products.append(normalized)
            except Exception as exc:
                logger.debug("No se pudieron enriquecer productos desde regex local: %s", exc)

            products.extend(self.entity_extractor.extract_products(raw_text))

        merged: Dict[int, Dict[str, Any]] = {}
        for prod in products:
            try:
                product_id = int(prod["id"])
            except Exception:
                continue
            if product_id in merged:
                merged[product_id]["cantidad_solicitada"] += float(prod.get("cantidad_solicitada", 0) or 0)
            else:
                merged[product_id] = prod

        parsed.products = list(merged.values())
        if parsed.products and parsed.intent in ("pedido", "cotizacion"):
            parsed.source = f"{getattr(parsed, 'source', '')}+catalog".strip("+")
        return parsed
