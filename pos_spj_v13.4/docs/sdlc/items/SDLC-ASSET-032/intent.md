# SDLC-ASSET-032 — Activos fuera de la replicación offline; los conflictos existen solo como vocabulario

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §105, §106 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-011, SDLC-SYNC-005, SDLC-ARQ-SYNC-001

## Problema
§105 pide que consulta, escaneo, inventario físico, inspecciones y OT asignadas funcionen offline con outbox y estado de sincronización. Activos no participa en la replicación y el conflicto offline es solo vocabulario.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/infrastructure/sync/replication_sources.py:132-148` — sin fuente de activos
- `backend/domain/assets/entities/asset_sync_conflict.py:1-21` — «solo vocabulario»

## Impacto
Multi-sucursal: los activos de una sucursal no se ven en el central.

## Objetivo
- Mutaciones de Activos replicadas con el sobre único y conflictos que no se sobrescriben en silencio.
- Pruebas.

## Alcance
- **Incluye:** Fuente de replicación y conflictos de Activos.
- **No incluye:** El transporte de replicación en sí (SDLC-SYNC-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- Memoria pipeline híbrido SQLite+PostgreSQL (Slices 0-6)

## Preguntas abiertas
- Ninguna por ahora.
