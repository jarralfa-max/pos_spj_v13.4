# SDLC-SYNC-002 — Hecho en CONFLICTO reenviado se marca SYNCED y nunca se proyecta

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-001

## Problema
Cuando la ingesta central guarda un hecho con `status='CONFLICT'` (regresión de versión), el reintento local reenvía el mismo sobre; la ingesta encuentra el mismo hash y responde DUPLICATE, que la estación cuenta como asentado y marca SYNCED. La proyección sólo lee `APPLIED`. El movimiento de caja o la venta nunca llega a los libros centrales y nadie se entera.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sync/central_ingestion.py:166-176,192-194` — CONFLICT guardado; mismo hash → DUPLICATE
- `backend/application/cash_register/offline_sync.py:170-171,199` y `replication_repository.py:179-187` — RETRY_LOCAL reenvía el sobre idéntico
- `backend/shared/sync/replication_envelope.py:301-303` — DUPLICATE cuenta como asentado
- `replication_outbox.py:224-227` — la estación marca SYNCED
- `backend/infrastructure/central/projection_repository.py:34` — proyección sólo `status='APPLIED'`

## Impacto
Pérdida silenciosa de dinero en el consolidado central (ventas, caja) en cuanto haya estaciones replicando.

## Objetivo
- Un hecho en CONFLICTO nunca deja la estación en SYNCED sin una resolución explícita.
- Existe un estado/consulta de conflictos pendientes visible para el responsable.
- Prueba de regresión: conflicto → reintento → el estado local sigue pendiente/conflicto.

## Alcance
- **Incluye:** Semántica DUPLICATE vs CONFLICT en ingesta y en la estación; prueba de regresión.
- **No incluye:** Política de resolución de conflictos por tipo de agregado (se define en Design).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Pipeline híbrido Slices 3-6.

## Preguntas abiertas
- ¿Quién resuelve un conflicto (central, estación, humano) y con qué pantalla?
