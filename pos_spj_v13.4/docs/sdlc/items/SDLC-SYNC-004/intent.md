# SDLC-SYNC-004 — Huecos en la secuencia de estación bloquean la recuperación de dispositivo

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-001

## Problema
Un sobre DEAD consume número de secuencia y nunca se envía; los hechos SEQUENCE_REUSED/EVENT_ID_REUSED tampoco se insertan. El `last_sequence` central sólo avanza con números contiguos; al re-enrolar en modo RECOVERY la estación reanuda desde ese número, reutiliza números que el central ya tiene, y cada uno recibe CONFLICT: la sincronización se detiene.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sync/replication_outbox.py:148,163-171`
- `backend/infrastructure/central/sync_inbox_repository.py:69-90`
- `backend/application/sync/device_provisioning.py:268`; `replication_repository.py:37-55`
- `backend/application/sync/central_ingestion.py:168-172`

## Impacto
Una estación recuperada deja de sincronizar indefinidamente.

## Objetivo
- La recuperación reanuda desde la secuencia máxima conocida por cualquiera de las dos partes.
- Los huecos por sobres DEAD quedan explicados (tombstone) y no detienen el avance.
- Prueba de recuperación con un hueco.

## Alcance
- **Incluye:** Outbox de replicación, provisión de dispositivo, ingesta.
- **No incluye:** Transporte (SYNC-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Pipeline híbrido.

## Preguntas abiertas
- Ninguna por ahora.
