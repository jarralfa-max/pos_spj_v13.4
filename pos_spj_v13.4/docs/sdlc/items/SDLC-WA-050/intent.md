# SDLC-WA-050 — Eliminación del legacy del canal: bridge con escrituras, orquestador, sender, webhook y notify v1, eventos y migraciones

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §74, §80, §81 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019, SDLC-WA-021, SDLC-WA-028, SDLC-WA-029, SDLC-WA-035, SDLC-WA-037, SDLC-WA-049

## Problema
Sigue vivo todo lo que §74 pide eliminar: `ERPBridge` con 24 sentencias de escritura a tablas del ERP en 7 archivos, `BusinessOrchestrator` (muerto en vivo), sender legacy (29 consumidores), webhook legacy, `/api/notify` v1, `WAEventEmitter`, `whatsapp_queue`, `wa_event_log`, tablas runtime en `conversations.db` y migraciones legacy 036/042/050/081/086/087/090.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/erp/bridge.py:332,475,485,496,612,701,710,767,850,920,924,998,1039`; `erp/gateways/payment_gateway.py:25,49,53`; `erp/gateways/delivery_gateway.py:26`
- `whatsapp_service/erp/business_orchestrator.py:44`; consumidor `flows/base_flow.py:14,35-39`
- `whatsapp_service/erp/events.py`; `main.py:116-118`
- Inventario completo: `arquitectura/matriz-whatsapp.md` §74

## Impacto
Dos arquitecturas en paralelo; cualquier arreglo hay que hacerlo dos veces.

## Objetivo
- Cada elemento de la tabla de §80 con consumidores = 0 y borrado; allowlist de SDLC-WA-049 vacía; bootstrap limpio funciona.

## Alcance
- **Incluye:** Borrado del legacy con cero consumidores.
- **No incluye:** Construir reemplazos (ítems de los que depende).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-21 (omitido por decisión del responsable); SDLC-WA-019.

## Preguntas abiertas
- Misma decisión que SDLC-WA-019: ¿se levanta el diferimiento de WA-21?
