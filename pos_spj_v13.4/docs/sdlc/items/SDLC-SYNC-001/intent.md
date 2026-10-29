# SDLC-SYNC-001 — Servidor central no aplica p006: toda petición de sync revienta en BD nueva

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El carril de migraciones PostgreSQL termina en p005; `p006_device_provisioning` existe pero no está registrada. El repositorio de estaciones ya selecciona las columnas que p006 agrega, así que en un servidor central migrado desde cero cada `/api/v1/sync/events` y cada consulta de dispositivo falla con columna inexistente.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/engine.py:475-481` — `PG_MIGRATIONS` llega a p005 *(verificado directamente en el triage)*
- `migrations/pg/p006_device_provisioning.py` existe y no aparece en la lista *(verificado directamente en el triage)*
- `backend/infrastructure/central/sync_inbox_repository.py:36-39,52-55` selecciona `public_key`, `key_algorithm`, `workstation_type`, `is_admin_station`… *(verificado directamente en el triage)*
- `backend/api/central_app.py:52-55` llama `get_station` en cada petición de sync
- Relacionado: `migrations/standalone/354_device_enrollment.py` tampoco está registrada en SQLite y nada lee `device_enrollment` (no verificado si debe existir)

## Impacto
Sincronización central caída en cualquier despliegue nuevo; ninguna estación puede replicar. Hoy no hay estaciones replicando en producción (ver SDLC-SYNC-005), por eso no hay pérdida aún.

## Objetivo
- Un PostgreSQL vacío migrado con `PG_MIGRATIONS` acepta `/api/v1/sync/events` y alta de dispositivo.
- Una prueba (job `central-postgres`) falla si existe un archivo `migrations/pg/p*.py` no registrado.
- Decisión explícita sobre `354_device_enrollment` (registrar o eliminar).

## Alcance
- **Incluye:** Registro de p006, guardia de 'migración no registrada' para el carril PG, decisión sobre 354.
- **No incluye:** Cambios de esquema nuevos; transporte de estaciones (SDLC-SYNC-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria del proyecto: pipeline híbrido SQLite+PostgreSQL, Slices 0-6 (2026-10-23/25). Commit `41618203` ya tocó `schema_target()` del carril PG.

## Preguntas abiertas
- ¿`354_device_enrollment` es parte del mismo slice que p006 o es un remanente a borrar?
