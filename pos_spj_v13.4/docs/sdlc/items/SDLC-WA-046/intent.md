# SDLC-WA-046 — Logs del canal sin correlación y sin métricas de entrega, resolución o latencia

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §57 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019

## Problema
Los logs no llevan `correlation_id`, `conversation_id` ni `operation_id`; el `X-Correlation-Id` del ERP no se propaga. No hay tasas de entrega, lectura, resolución de intención, handoff, conversión, abandono ni latencia del proveedor o del ERP.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/router/message_router.py:247`; `backend/infrastructure/integrations/whatsapp_client.py:73-83`
- `whatsapp_service/application/diagnostics_service.py:43-119` — solo conteos
- Pruebas: `whatsapp_service/tests/test_diagnostics_service.py`

## Impacto
Diagnóstico lento de incidentes.

## Objetivo
- Correlación propagada de punta a punta y métricas de §57 calculadas en backend.

## Alcance
- **Incluye:** Logging estructurado y métricas del canal.
- **No incluye:** Health (SDLC-WA-017).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-20 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
