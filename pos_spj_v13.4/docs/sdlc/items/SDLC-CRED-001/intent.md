# SDLC-CRED-001 — Exposición de crédito suma la tabla legacy cuentas_por_cobrar que ya nadie escribe

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El resumen de cuentas por cobrar suma `cuentas_por_cobrar` (legacy) y `receivables` (canónica): lectura dual prohibida por la REGLA CERO. La propia docstring admite que nadie escribe la tabla legacy; la deuda legacy no puede abonarse por ninguna ruta viva y la exposición de esos clientes queda inflada para siempre.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/customer_credit/queries/customer_accounts_receivable_summary_query.py:97-114,157` (docstring línea 100)

## Impacto
Clientes bloqueados por límite de crédito con deuda que no pueden pagar; reportes de CxC incorrectos.

## Objetivo
- Existe una única fuente de saldo de crédito (`receivables`).
- Los saldos legacy pendientes se migran (o se cierran con decisión documentada) sobre copia de la BD real antes del corte.
- Prueba: un cliente con saldo legacy migrado puede abonar y su exposición baja.

## Alcance
- **Incluye:** Consulta de resumen, migración de saldos legacy.
- **No incluye:** Otras tablas legacy de clientes (SDLC-CRM-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: SALES/CRM transformaciones; REGLA CERO de `SPJ_REFACTOR_SKILL.md`.

## Preguntas abiertas
- ¿Hay saldos vivos en `cuentas_por_cobrar` en la BD real? (se medirá sobre copia)
