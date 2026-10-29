# SDLC-CASH-001 — Reversa de venta registra la salida de efectivo en el turno original, aunque esté cerrado

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Al reversar una venta completada, la salida de efectivo se escribe en el turno original sin verificar su estado, y quien reversa no necesita turno abierto (a diferencia de la devolución parcial). Si el turno original ya tuvo corte Z, la devolución queda en un turno cerrado mientras el efectivo sale del cajón actual; el Z del cajero actual muestra faltante y la cuenta 1102 queda con saldo residual.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/use_cases/return_use_cases.py:190-268` (vs ~185 para devolución parcial)
- `backend/application/cash_register/sales_integration.py:231-240`
- `backend/application/event_handlers/finance/cash_shift_closed_handler.py:66-71`
- `migrations/standalone/175_cash_register_bounded_context_schema.py:243-249` — sin trigger/guardia en `cash_ledger_entries`
- Efecto inferido del código, **no ejecutado**

## Impacto
Cajeros y gerencia: faltantes falsos en el corte; descuadre entre caja y mayor.

## Objetivo
- Una reversa exige turno abierto del operador y registra la salida en ese turno.
- Ningún movimiento se escribe en un turno cerrado (guardia en repositorio o BD).
- Prueba de regresión: venta en turno A, Z de A, reversa en turno B → B refleja la salida, A no cambia, mayor cuadra.

## Alcance
- **Incluye:** Caso de uso de reversa, integración Caja, guardia de turno cerrado.
- **No incluye:** Devoluciones parciales (ya exigen turno).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: CASH-26, CASH-AUD 968e0bc (regla de propiedad del turno), SALES-AUD cebf67a.

## Preguntas abiertas
- Ninguna por ahora.
