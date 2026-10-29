# SDLC-SALES-003 — Outbox de ventas sin contador de intentos ni dead-letter: un evento envenenado se reintenta para siempre

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`sales_outbox` no tiene contador de intentos, dead-letter ni error registrado (Caja y Finanzas sí). Un `SALE_COMPLETED` que siempre falla se reintenta en cada operación del POS y sólo aparece en el log; la venta nunca llega al mayor.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/integrations/wiring.py:88-123`
- `backend/infrastructure/db/repositories/sales/outbox_repository.py:28-42`
- Comparar: `backend/application/cash_register/finance_wiring.py:45,98-109`, `backend/application/services/finance/outbox_dispatcher.py:24,31-50`

## Impacto
Ventas que nunca se contabilizan, invisibles para Finanzas.

## Objetivo
- El outbox de ventas registra intentos y último error y pasa a DEAD tras N intentos.
- Los eventos DEAD son visibles en una consulta/pantalla de salud.
- Migración probada sobre copia de BD real.

## Alcance
- **Incluye:** Esquema y despachador del outbox de ventas (migración nueva).
- **No incluye:** Otros outbox (HR-002, PROC-003, ORD-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria SALES-AUD cebf67a.

## Preguntas abiertas
- Ninguna por ahora.
