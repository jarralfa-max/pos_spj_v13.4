# SDLC-CORE-008 — Guardias de arquitectura en rojo por DDL fuera de migraciones, conexiones crudas y ratchet UUID

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
De 904 pruebas de `tests/architecture`, 22 fallan. Las que protegen integridad: un repositorio emite DDL (`ALTER TABLE product_unit_conversions`), `account_recovery_schema` agrega DDL nuevo fuera de migraciones, `finance_schema.py` abre una conexión SQLite cruda, y el ratchet de identidad UUID sube `legacy_id` de 2 a 7 (las 4 nuevas son una variable local en la migración 318 — probable falso positivo, **no verificado** si conserva el id legacy como identidad).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/sdlc/baseline/2026-10-28.md` — `22 failed, 879 passed, 1 skipped, 2 xfailed in 1301.95s` *(verificado directamente en el triage)*
- `tests/architecture/test_clean_birth_guardrails.py::test_services_repositories_ui_do_not_create_schema` y `test_no_schema_changes_outside_migrations.py` — `backend/infrastructure/db/repositories/products/unit_repository.py:86`, `backend/infrastructure/db/schema/account_recovery_schema.py` *(verificado directamente en el triage)*
- `tests/architecture/test_no_raw_sqlite_connect.py` — `backend/infrastructure/db/schema/finance_schema.py:952` *(verificado directamente en el triage)*
- `tests/architecture/test_uuidv7_cutover_protection.py:17` baseline `legacy_id: 2`; coincidencias actuales en `migrations/standalone/318_quotes_bounded_context.py:60-84`, `196_customer_credit_profile_backfill.py`, `tools/refactor_control/build_cutover_spec.py:20` *(verificado directamente en el triage)*
- `tests/architecture/test_no_legacy_imports.py` — 4 imports prohibidos (`migrations`, `migrations.engine`, `scripts.verify_tables`) *(verificado directamente en el triage)*

## Impacto
Las guardias que protegen la REGLA CERO y el esquema born-clean dejaron de proteger (están rojas, nadie las mira).

## Objetivo
- Las guardias de esquema, conexión e identidad vuelven a verde corrigiendo el código o, si es falso positivo, ajustando el patrón con justificación escrita (nunca subiendo el baseline sin evidencia).

## Alcance
- **Incluye:** Las 5 guardias citadas.
- **No incluye:** Guardias de UI/diseño y de herramientas (SDLC-CORE-009).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: suites de arquitectura con fallas preexistentes.

## Preguntas abiertas
- Ninguna por ahora.
