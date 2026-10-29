# SDLC-LOSS-001 — Mermas: ningún caso puede aprobarse, y al habilitarlo una revaluación asentaría doble

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`LossCase.approve()` existe pero ningún caso de uso, fábrica ni pantalla la invoca; el posteo a inventario y la valuación exigen `APPROVED`. Una merma registrada nunca baja stock ni llega al mayor. Además, nada impide valuar dos veces el mismo caso: cada valuación nueva emite reconocimiento por el monto completo y Finanzas lo asienta por `valuation_id`, así que en cuanto exista la aprobación habrá doble asiento. La reversa de inventario (`LOSS_INVENTORY_REVERSED`) no tiene consumidor.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/losses/entities/loss_case.py:70` — `approve()`
- Grep: la única llamada `.approve(` en Mermas es `backend/application/losses/recovery.py:118` (recuperaciones, no casos) *(verificado directamente en el triage)*
- `backend/application/losses/loss_inventory_integration.py:75,88`, `valuation.py:29` — exigen APPROVED
- `backend/infrastructure/desktop/losses_factory.py:213-222` — servicios construidos, sin llamador
- `backend/application/losses/valuation.py:21-38`, `backend/infrastructure/persistence/loss_valuation_repository.py:22`, `migrations/standalone/174_losses_bounded_context_schema.py:131`, `backend/application/event_handlers/finance/loss_recognition_handler.py:48` — revaluación = asiento nuevo
- `loss_inventory_integration.py:139` — `LOSS_INVENTORY_REVERSED` sin consumidor

## Impacto
Mermas reales nunca descargan inventario ni gasto: el stock queda inflado y el margen sobrestimado. Al corregir sólo la aprobación se introduce doble asiento (dinero).

## Objetivo
- Existe flujo revisión → aprobación con permiso `MERMAS.*` y segregación (quien registra ≠ quien aprueba).
- Aprobar descarga inventario una vez y asienta una vez.
- Revaluar asienta sólo la diferencia (o reversa + nuevo), nunca el total de nuevo.
- Reversar inventario reversa el asiento.

## Alcance
- **Incluye:** Caso de uso + UI de aprobación, idempotencia de valuación/asiento, consumidor de la reversa.
- **No incluye:** Mermas de transferencia (SDLC-TRF-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: alcance por sucursal de Mermas (2026-09-17); permisos estándar `MODULO.accion`.

## Preguntas abiertas
- ¿Umbral de monto a partir del cual la aprobación requiere gerente?
- Revaluación: ¿ajuste por diferencia o reversa total + asiento nuevo?
