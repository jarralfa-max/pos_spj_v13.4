# SDLC-CASH-002 — Depósito de caja confirmado nunca se asienta al banco

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`TreasuryCashDepositConfirmedHandler` (Dr banco / Cr caja) no puede ejecutarse: `TREASURY_CASH_DEPOSIT_CONFIRMED` no tiene publicador ni está en `FINANCE_EVENTS`. El depósito preparado en Caja no llega al banco; la única ruta es una transferencia manual sin vínculo al `deposit_id`, con riesgo de omisión o doble registro.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/finance/cash_finance_router.py:21`
- `backend/application/cash_register/finance_wiring.py:35-41`
- `backend/shared/events/event_names.py:86`

## Impacto
Conciliación bancaria manual y propensa a error.

## Objetivo
- Confirmar un depósito asienta una vez, ligado al `deposit_id`.

## Alcance
- **Incluye:** Publicador y ruta en Finanzas.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
CASH-26, FIN-ERP round 2.

## Preguntas abiertas
- ¿Quién confirma el depósito (cajero, tesorería) y con qué evidencia?
