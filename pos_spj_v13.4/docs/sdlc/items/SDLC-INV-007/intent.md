# SDLC-INV-007 — Báscula simulada (StubScaleGateway) cableada en la composición de Inventario; doble mecanismo de retención de calidad

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
La composición de Inventario cablea `StubScaleGateway`: no hay driver real de báscula en ese módulo (Ventas tiene `scale_reading_service`). Además, la docstring de `inspect_receipt.py` describe dos retenciones de calidad que no se ven entre sí (`quality_status` del lote y la cubeta `PENDING_INSPECTION`) — **no verificado** más allá de la docstring.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/inventory/composition.py:102-109`
- `backend/application/inventory/use_cases/inspect_receipt.py:1-15`

## Impacto
Capturas de peso en Inventario no usan báscula real.

## Objetivo
- Inventario usa el mismo gateway de báscula que Ventas; decisión sobre la retención de calidad.

## Alcance
- **Incluye:** —
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
