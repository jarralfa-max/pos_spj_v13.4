# SDLC-WA-023 — Resolución de intención viva fuera de orden: la IA corre antes que las capas deterministas y su salida no se valida

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §27, §28, §29, §30 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-022, SDLC-WA-007

## Problema
Con IA activa, el resolvedor vivo consulta a la IA antes que respuestas interactivas y reglas; no hay capa de estado esperado ni handoff final. La IA "en la nube" es un simulador por palabras clave; el único LLM real (Ollama) devuelve intenciones sin validar contra un catálogo y con confianza fija de 0.80. La IA fija tipo de entrega y fecha programada sin validación. De las 25 intenciones del documento, 11 no existen en vivo (CHECK_PRICE, CHECK_STOCK, TRACK_DELIVERY, CHECK_LOYALTY, HUMAN_HANDOFF, OPT_OUT…). Hay cuatro vocabularios de intención distintos. El servicio canónico de resolución por capas existe sin uso.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/ai/intent_resolver.py:49-110`; `parser/intent_parser.py:52-75,83-96,138-162`
- `whatsapp_service/ai/intent_ai_client.py:45-69` (simulador); `parser/llm_local.py:33,111-114`
- `whatsapp_service/router/message_router.py:345-353` — `delivery_type`/`scheduled_at` sin validar
- Vocabularios: `parser/patterns.py:12-50`; `ai/intent_schema.py:9-27`; `parser/llm_local.py:33`; `domain/whatsapp/enums.py:121-151`
- Canon: `whatsapp_service/application/intent_resolution_service.py:92-143`
- Pruebas: `whatsapp_service/tests/test_intent_resolution_service.py` (canon); `test_intent_resolver_ai_paths.py` (vivo, 5 fallan hoy)

## Impacto
Clientes mal entendidos; riesgo de que una respuesta del LLM dispare acciones no confirmadas.

## Objetivo
- Un solo resolvedor por capas en el orden de §28 con catálogo de intenciones y entidades tipadas y validadas.
- La IA solo clasifica o extrae; ninguna salida de IA ejecuta una operación sin caso de uso y confirmación (prueba de arquitectura).

## Alcance
- **Incluye:** Resolución de intención en el camino vivo.
- **No incluye:** Escritura de `configuraciones` por la IA (SDLC-WA-007).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-8 (memoria).

## Preguntas abiertas
- Presupuesto $0: ¿se permite algún LLM en la nube, o solo Ollama local (y en qué máquina corre)?
