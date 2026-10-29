# SDLC-SALES-004 — Expiración de ventas suspendidas sin llamador e insegura si se cablea

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`ExpireSuspendedSalesUseCase` no tiene llamador en producción. Si se cableara, `sale.cancel()` lanza para ventas con pagos y abortaría el lote completo; además no cancela el cargo a crédito registrado al pagar, así que suspendidas pagadas a crédito mantienen una CxC viva que consume límite.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/use_cases/suspension_sweep_use_cases.py:46-69`
- `backend/domain/sales/entities.py:516-518`; `backend/domain/sales/policies/lifecycle_policies.py:97-101`
- `backend/application/sales/use_cases/payment_use_cases.py:118-122`

## Impacto
Ventas suspendidas acumuladas y crédito consumido por ventas nunca concluidas.

## Objetivo
- Barrido por venta (una falla no aborta las demás).
- Expirar revierte pagos/cargos a crédito.
- Planificado en el ciclo periódico.

## Alcance
- **Incluye:** Caso de uso de barrido y su programación.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SALES-AUD.

## Preguntas abiertas
- ¿Vigencia de una venta suspendida?
