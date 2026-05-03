# parser/intent_parser.py — Motor de intenciones de 3 niveles
"""
Nivel 1: Botones interactivos → acción directa (70%)
Nivel 2: Regex + keywords → intención (20%)
Nivel 3: DeepSeek/Ollama → entendimiento profundo (10%)

El LLM solo se invoca si Nivel 1 y 2 fallan.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional
from models.message import IncomingMessage, MessageType, InteractiveType
from parser.patterns import detect_intent, extract_product_mentions, extract_number
from parser.product_matcher import ProductMatcher
from parser.llm_local import OllamaClient

logger = logging.getLogger("wa.parser")


class ParsedIntent:
    """Resultado del parsing de un mensaje."""

    def __init__(self, intent: str, confidence: float = 1.0,
                 action_id: str = "", products: List[Dict] = None,
                 number: float = 0.0, raw_text: str = "",
                 source: str = ""):
        self.intent = intent
        self.confidence = confidence
        self.action_id = action_id
        self.products = products or []
        self.number = number
        self.raw_text = raw_text
        self.source = source       # "button", "regex", "llm", "fallback"

    def __repr__(self):
        return (f"ParsedIntent({self.intent}, conf={self.confidence:.2f}, "
                f"src={self.source}, action={self.action_id})")


class IntentParser:
    """Parsea mensajes de WhatsApp en intenciones accionables."""

    def __init__(self, product_matcher: ProductMatcher,
                 llm_client: Optional[OllamaClient] = None):
        self.matcher = product_matcher
        self.llm = llm_client or OllamaClient()

    async def parse(self, msg: IncomingMessage) -> ParsedIntent:
        """Parsea un mensaje en una intención — 3 niveles."""

        # ── Nivel 1: Botón/Lista interactiva → acción directa ─────────────
        if msg.type == MessageType.INTERACTIVE:
            return self._parse_interactive(msg)

        # ── Nivel 2: Texto libre → regex + keywords ───────────────────────
        if msg.type == MessageType.TEXT and msg.text:
            result = self._parse_regex(msg.text)
            if result.intent != "unknown":
                return result

            # ── Nivel 3: DeepSeek/Ollama → entendimiento profundo ─────────
            llm_result = await self._parse_llm(msg.text)
            if llm_result and llm_result.intent != "unknown":
                return llm_result

            # Devolver el resultado del regex (unknown) con texto original
            return result

        # ── Tipo no soportado ─────────────────────────────────────────────
        return ParsedIntent(intent="unknown", confidence=0.0,
                            raw_text=msg.text, source="fallback")

    def _parse_interactive(self, msg: IncomingMessage) -> ParsedIntent:
        """Nivel 1: Respuesta a botón o lista interactiva."""
        action_id = msg.interactive_id
        parts = action_id.split("_", 2)
        prefix = parts[0] if parts else ""

        intent_map = {
            "menu": "menu_action",
            "cat": "select_category",
            "prod": "select_product",
            "qty": "select_quantity",
            "confirm": "confirm",
            "cancel": "cancel",
            "entrega": "select_entrega",
            "pago": "select_pago",
            "suc": "select_sucursal",
            "mas": "add_more",
            "repetir": "repetir",
            "estado": "estado_pedido",
        }

        intent = intent_map.get(prefix, "interactive_action")

        return ParsedIntent(
            intent=intent, confidence=1.0,
            action_id=action_id, raw_text=msg.interactive_title,
            source="button")

    def _parse_regex(self, text: str) -> ParsedIntent:
        """Nivel 2: Regex + keywords."""
        text = text.strip()
        intent, confidence = detect_intent(text)

        products = []
        if intent in ("pedido", "cotizacion"):
            raw_mentions = extract_product_mentions(text)
            for mention in raw_mentions:
                match = self.matcher.match_single(mention["nombre_raw"])
                if match:
                    products.append({
                        **match,
                        "cantidad_solicitada": mention["cantidad"],
                        "unidad_solicitada": mention["unidad"],
                    })

        number = extract_number(text)

        return ParsedIntent(
            intent=intent, confidence=confidence,
            products=products, number=number,
            raw_text=text, source="regex")

    async def _parse_llm(self, text: str) -> Optional[ParsedIntent]:
        """Nivel 3: DeepSeek via Ollama."""
        try:
            # Dar hint del catálogo al modelo
            catalogo_nombres = [p["nombre"] for p in self.matcher._cache[:30]]

            result = await self.llm.parse_message(text, catalogo_nombres)
            if not result:
                return None

            intent = result.get("intent", "unknown")
            if intent == "unknown":
                return None

            # Resolver productos mencionados por el LLM contra el catálogo real
            products = []
            for p in result.get("products", []):
                name = p.get("name", "")
                qty = float(p.get("qty", 0))
                if name:
                    match = self.matcher.match_single(name)
                    if match:
                        products.append({
                            **match,
                            "cantidad_solicitada": qty or 1.0,
                            "unidad_solicitada": p.get("unit", "kg"),
                        })

            logger.info("LLM parsed: intent=%s, products=%d, text='%s'",
                         intent, len(products), text[:50])

            return ParsedIntent(
                intent=intent, confidence=0.80,
                products=products, raw_text=text,
                source="llm")

        except Exception as e:
            logger.debug("LLM parse failed: %s", e)
            return None
