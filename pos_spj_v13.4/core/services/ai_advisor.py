# core/services/ai_advisor.py — SPJ POS v13.30 — FASE 8
"""
AIAdvisor — Asesor estratégico con IA local (DeepSeek/Ollama).

IMPORTANTE:
    - Controlado por toggle ai_enabled
    - NUNCA ejecuta acciones — solo analiza y sugiere
    - Si Ollama no está disponible, todo funciona sin IA
    - Usa datos reales del TreasuryService y AlertEngine

Responde preguntas tipo CFO:
    "¿Debería abrir otra sucursal?"
    "¿Vale la pena invertir en nuevo equipo?"
    "¿Cómo optimizar la nómina?"
    "¿El programa de fidelización es rentable?"

USO:
    advisor = container.ai_advisor
    resp = await advisor.consultar("¿Debería abrir otra sucursal en el norte?")
    resp = advisor.analisis_rapido()  # análisis sin prompt del usuario
"""
from __future__ import annotations
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("spj.ai")

SYSTEM_PROMPT = """Eres el CFO y COO virtual de una carnicería/abarrotera mexicana con múltiples sucursales.
Analizas datos financieros reales y das recomendaciones estratégicas.

REGLAS:
1. Responde en español, directo, con números concretos
2. NUNCA inventes datos — usa solo los que te proporcionan
3. Da recomendaciones accionables con impacto estimado
4. Identifica riesgos y oportunidades
5. Prioriza la rentabilidad y el flujo de caja
6. Sé conservador en proyecciones

Formato de respuesta:
📊 ANÁLISIS: (qué dicen los datos)
💡 RECOMENDACIÓN: (qué hacer)
⚠️ RIESGOS: (qué podría salir mal)
📈 IMPACTO ESTIMADO: (números)"""


class AIAdvisor:
    """Asesor estratégico con IA local."""

    def __init__(self, db_conn=None, treasury_service=None,
                 alert_engine=None, decision_engine=None,
                 module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self.alerts = alert_engine
        self.decisions = decision_engine
        self._module_config = module_config
        self._ollama_url = "http://localhost:11434"
        self._model = "deepseek-r1:8b"
        self._available: Optional[bool] = None
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass
        self._ensure_table()

    def _ensure_table(self):
        if not self.db:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS ai_consulta_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    pregunta TEXT DEFAULT '',
                    respuesta TEXT DEFAULT '',
                    datos_contexto TEXT DEFAULT '{}',
                    disponible INTEGER DEFAULT 0,
                    fecha TEXT DEFAULT (datetime('now'))
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    def _persist_consulta(self, tipo: str, pregunta: str,
                           respuesta: str, contexto: dict,
                           disponible: bool) -> None:
        if not self.db:
            return
        try:
            self.db.execute(
                "INSERT INTO ai_consulta_log "
                "(tipo, pregunta, respuesta, datos_contexto, disponible) "
                "VALUES (?,?,?,?,?)",
                (tipo, pregunta[:500], respuesta[:2000],
                 json.dumps(contexto, default=str)[:2000],
                 1 if disponible else 0))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass
        # Publicar evento
        if self._bus:
            try:
                from core.events.event_bus import AI_CONSULTA_REALIZADA
                self._bus.publish(AI_CONSULTA_REALIZADA, {
                    "tipo":          tipo,
                    "pregunta":      pregunta[:200],
                    "disponible":    disponible,
                    "tiene_alertas": bool(contexto.get("alertas_activas", 0)),
                }, async_=True)
            except Exception:
                pass

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('ai')
        return False  # Desactivado por defecto

    async def is_available(self) -> bool:
        """Verifica si Ollama está corriendo."""
        if not self.enabled:
            return False
        if self._available is not None:
            return self._available
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._ollama_url}/api/tags")
                self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def is_available_sync(self) -> bool:
        """Versión síncrona de is_available."""
        if not self.enabled:
            return False
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._ollama_url}/api/tags")
            req.method = 'GET'
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ══════════════════════════════════════════════════════════════════════════
    #  Consulta libre (CFO virtual)
    # ══════════════════════════════════════════════════════════════════════════

    async def consultar(self, pregunta: str) -> Dict[str, Any]:
        """
        Consulta estratégica al IA con contexto financiero real.
        Retorna {"respuesta": str, "datos_usados": dict, "disponible": bool}
        """
        if not self.enabled:
            return {"respuesta": "IA desactivada. Activa el toggle ai_enabled.",
                    "disponible": False}

        if not await self.is_available():
            return {"respuesta": "Ollama no disponible. Verifica que esté corriendo.",
                    "disponible": False}

        # Obtener contexto financiero real
        contexto = self._build_context()

        prompt = (
            f"DATOS FINANCIEROS ACTUALES DEL NEGOCIO:\n"
            f"```json\n{json.dumps(contexto, indent=2, ensure_ascii=False)}\n```\n\n"
            f"PREGUNTA DEL DUEÑO:\n{pregunta}"
        )

        try:
            respuesta = await self._call_ollama(prompt)
            resultado = {
                "respuesta": respuesta,
                "datos_usados": contexto,
                "disponible": True,
                "timestamp": datetime.now().isoformat(),
            }
            self._persist_consulta("llm", pregunta, respuesta, contexto, True)
            return resultado
        except Exception as e:
            logger.error("AI consulta error: %s", e)
            self._persist_consulta("llm_error", pregunta, str(e), contexto, True)
            return {"respuesta": f"Error: {e}", "disponible": True}

    # ══════════════════════════════════════════════════════════════════════════
    #  Análisis rápido (sin pregunta del usuario)
    # ══════════════════════════════════════════════════════════════════════════

    def analisis_rapido(self) -> Dict[str, Any]:
        """
        Análisis ejecutivo SIN IA — usa reglas del DecisionEngine.
        Funciona SIEMPRE, con o sin Ollama.
        """
        resultado = {
            "kpis": {},
            "alertas_criticas": [],
            "sugerencias": [],
            "salud": "",
            "timestamp": datetime.now().isoformat(),
        }

        # KPIs
        if self.treasury:
            try:
                resultado["kpis"] = self.treasury.estado_cuenta()
                resultado["salud"] = resultado["kpis"].get("salud", "")
            except Exception:
                pass

        # Alertas
        if self.alerts:
            try:
                alertas = self.alerts.get_alerts(severity="critical", limit=5)
                resultado["alertas_criticas"] = alertas
            except Exception:
                pass

        # Sugerencias
        if self.decisions:
            try:
                sug = self.decisions.generar_sugerencias()
                resultado["sugerencias"] = sug[:10]
            except Exception:
                pass

        self._persist_consulta(
            "analisis_rapido", "", "",
            {"kpis": resultado.get("kpis", {}),
             "alertas": len(resultado.get("alertas_criticas", [])),
             "sugerencias": len(resultado.get("sugerencias", []))},
            disponible=True)
        return resultado

    # ══════════════════════════════════════════════════════════════════════════
    #  Evaluaciones específicas
    # ══════════════════════════════════════════════════════════════════════════

    async def evaluar_inversion(self, descripcion: str, monto: float) -> Dict:
        """Evalúa si una inversión específica vale la pena."""
        return await self.consultar(
            f"Evalúa esta inversión:\n"
            f"Descripción: {descripcion}\n"
            f"Monto: ${monto:,.2f}\n\n"
            f"¿Es buen momento para invertir? ¿El negocio tiene liquidez? "
            f"¿Cuál sería el ROI esperado?")

    async def evaluar_expansion(self, ubicacion: str = "") -> Dict:
        """Evalúa si abrir una nueva sucursal tiene sentido."""
        return await self.consultar(
            f"¿Debería abrir una nueva sucursal"
            f"{' en ' + ubicacion if ubicacion else ''}?\n"
            f"Considera: capital disponible, burn rate, margen actual, "
            f"carga de nómina, y rentabilidad de sucursales existentes.")

    async def optimizar_costos(self) -> Dict:
        """Sugiere cómo reducir costos."""
        return await self.consultar(
            "Analiza la estructura de costos y sugiere las 3 acciones más "
            "impactantes para reducir gastos sin afectar la operación.")

    # ══════════════════════════════════════════════════════════════════════════
    #  Internals
    # ══════════════════════════════════════════════════════════════════════════

    def _build_context(self) -> Dict:
        """Construye contexto financiero real para el prompt."""
        ctx = {}
        if self.treasury:
            try:
                ctx["finanzas"] = self.treasury.kpis_financieros()
            except Exception:
                pass
        if self.alerts:
            try:
                ctx["alertas_activas"] = len(
                    self.alerts.get_alerts(severity="critical"))
            except Exception:
                pass
        if self.decisions:
            try:
                sug = self.decisions.generar_sugerencias()
                ctx["sugerencias_pendientes"] = len(sug)
                ctx["top_sugerencias"] = [s.get("titulo", "") for s in sug[:3]]
            except Exception:
                pass
        return ctx

    async def _call_ollama(self, user_msg: str) -> str:
        """Llama a Ollama API."""
        import httpx
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 500},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/chat", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama HTTP {resp.status_code}")
        data = resp.json()
        return data.get("message", {}).get("content", "Sin respuesta")
