# parser/llm_local.py — DeepSeek via Ollama (Nivel 3 NLP)
"""
LLM local para mensajes que ni botones ni regex resolvieron.
Corre en el mismo servidor, $0 de costo.

Requisitos:
    1. Instalar Ollama: curl -fsSL https://ollama.com/install.sh | sh
    2. Descargar modelo: ollama pull deepseek-r1:8b
    3. Ollama corre automáticamente en localhost:11434

El modelo recibe SOLO el mensaje + catálogo reducido.
Responde SOLO JSON — sin explicaciones, sin markdown.
"""
from __future__ import annotations
import httpx
import json
import logging
from typing import Optional, Dict, List
from config.settings import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger("wa.llm")

# ── System prompt minimalista (menos tokens = más rápido) ─────────────────────
SYSTEM_PROMPT = """Eres un asistente de una carnicería/abarrotera mexicana.
Extrae la intención y productos del mensaje del cliente.

Intenciones posibles: pedido, cotizacion, repetir, estado_pedido, cancelar, saludo, ayuda, pago, unknown

Responde SOLO JSON válido, nada más. Sin explicaciones, sin markdown.

Formato:
{"intent":"pedido","products":[{"name":"pechuga","qty":5,"unit":"kg"}],"delivery":"domicilio","notes":""}

Si no hay productos: {"intent":"saludo","products":[],"notes":""}
Si no entiendes: {"intent":"unknown","products":[],"notes":""}"""


class OllamaClient:
    """Cliente para Ollama API local."""

    def __init__(self, url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.url = url.rstrip("/")
        self.model = model
        self._available: Optional[bool] = None

    async def is_available(self) -> bool:
        """Verifica si Ollama está corriendo."""
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.url}/api/tags")
                self._available = resp.status_code == 200
                if self._available:
                    models = [m.get("name", "") for m in resp.json().get("models", [])]
                    if not any(self.model.split(":")[0] in m for m in models):
                        logger.warning(
                            "Modelo '%s' no encontrado en Ollama. "
                            "Modelos disponibles: %s. "
                            "Ejecuta: ollama pull %s",
                            self.model, models, self.model)
                        self._available = False
                logger.info("Ollama disponible: %s, modelo: %s",
                            self._available, self.model)
        except Exception:
            self._available = False
            logger.info("Ollama no disponible en %s — Nivel 3 desactivado", self.url)
        return self._available

    async def parse_message(self, text: str,
                            catalogo_hint: List[str] = None) -> Optional[Dict]:
        """
        Envía mensaje al LLM local y parsea la respuesta JSON.
        
        Args:
            text: Mensaje del cliente
            catalogo_hint: Lista de nombres de productos para ayudar al modelo
            
        Returns:
            Dict con intent, products, etc. o None si falla
        """
        if not await self.is_available():
            return None

        # Agregar hint de catálogo al prompt si hay
        user_msg = text
        if catalogo_hint:
            productos_str = ", ".join(catalogo_hint[:30])
            user_msg = f"Catálogo: {productos_str}\n\nMensaje: {text}"

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,      # Más determinístico
                    "num_predict": 200,       # Limitar respuesta
                },
            }

            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.url}/api/chat", json=payload)

            if resp.status_code != 200:
                logger.warning("Ollama HTTP %d: %s",
                               resp.status_code, resp.text[:100])
                return None

            data = resp.json()
            content = data.get("message", {}).get("content", "")

            # Extraer JSON de la respuesta (puede venir con basura)
            return self._extract_json(content)

        except httpx.TimeoutException:
            logger.warning("Ollama timeout para: %s", text[:50])
            return None
        except Exception as e:
            logger.error("Ollama error: %s", e)
            return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extrae JSON válido del texto del LLM."""
        text = text.strip()

        # Intento 1: parsear directo
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Intento 2: buscar { ... } en el texto
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Intento 3: limpiar markdown fences
        for fence in ("```json", "```"):
            if fence in text:
                clean = text.split(fence)[-1].split("```")[0].strip()
                try:
                    return json.loads(clean)
                except json.JSONDecodeError:
                    pass

        logger.debug("No se pudo extraer JSON de: %s", text[:100])
        return None
