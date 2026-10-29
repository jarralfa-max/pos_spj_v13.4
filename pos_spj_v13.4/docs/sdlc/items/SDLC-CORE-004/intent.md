# SDLC-CORE-004 — Archivos de migración SQLite sin registrar y números duplicados

- **Prioridad:** P3
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
030, 032, 034, 048, 066, 076, 077, 093-095, 172, 173, 200 (excluida a propósito) y 354 no están en `MIGRATIONS`; 172 y 173 reutilizan números ya tomados por logística; hay `.sql` sueltos (`093-095*.sql`, `fix_finanzas_schema.sql`). BD nuevas obtienen esas columnas del esquema born-clean.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/engine.py:179-180`
- `migrations/standalone/` (lista)
- `backend/infrastructure/db/schema/inventory_schema.py:118,153`

## Impacto
Confusión y riesgo de ejecutar algo obsoleto.

## Objetivo
- Cada archivo se registra, se archiva o se elimina con decisión; prueba que detecte archivos no registrados (con lista de excepciones documentada).

## Alcance
- **Incluye:** migrations/.
- **No incluye:** 354 (SYNC-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
`scripts/audit_migrations.py`.

## Preguntas abiertas
- Ninguna por ahora.
