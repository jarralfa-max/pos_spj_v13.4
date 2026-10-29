# SDLC-INV-001 — Ajustes, diferencias de conteo y disposición de cuarentena sin asiento contable

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`INVENTORY_ADJUSTMENT_POSTED` se escribe en `inventory_outbox`, pero ese outbox sólo lo lee la replicación central; nada lo despacha localmente. `InventoryAdjustmentHandler` existe y nunca se suscribe (Finanzas sólo suscribe la ruta de mermas). La disposición de cuarentena postea `EXPIRY_DISPOSAL` directo, sin pasar por Mermas ni valuación. El inventario físico y la cuenta de inventario del mayor se separan.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/finance/wiring.py:22` — única ruta suscrita: `LOSS_FINANCE_RECOGNITION_REQUESTED` *(verificado directamente en el triage)*
- `backend/application/event_handlers/finance/inventory_adjustment_handler.py:13-16` — sin suscriptor (grep en backend/frontend) *(verificado directamente en el triage)*
- `backend/application/inventory/use_cases/adjustment_use_cases.py:236-244` — emite al outbox
- `backend/infrastructure/sync/replication_sources.py` — único lector de `inventory_outbox` *(verificado directamente en el triage)*
- `backend/application/inventory/use_cases/quarantine_use_cases.py:200-206` — disposición directa

## Impacto
Finanzas/gerencia: el mayor no refleja ajustes ni bajas por caducidad. Viola CLAUDE.md regla 11 (todo impacto financiero con asiento).

## Objetivo
- Cada ajuste, diferencia de conteo y disposición de cuarentena valorizada produce exactamente un asiento balanceado vía `registrar_asiento()` y deja rastro en `financial_event_log`.
- Reintentar el despacho no duplica asientos (idempotencia por `operation_id`).
- La disposición de cuarentena decide explícitamente si pasa por Mermas.

## Alcance
- **Incluye:** Despacho local del outbox de inventario hacia Finanzas, suscripción del handler, ruta de cuarentena.
- **No incluye:** Unificación de convenciones de ubicación (SDLC-INV-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: INV-25/INV-27; outbox de inventario sin drenar ya señalado en la memoria del corte del shell.

## Preguntas abiertas
- ¿Las bajas por caducidad son merma (Mermas valúa y asienta) o ajuste de inventario directo?
- ¿Qué cuentas usa un ajuste positivo (sobrante)?
