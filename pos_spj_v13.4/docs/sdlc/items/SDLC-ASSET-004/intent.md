# SDLC-ASSET-004 — Seis tablas legacy de activos se siguen creando sin lector ni escritor, con dinero en REAL

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §5, §12, §109 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`activos`, `mantenimientos`, `assets`, `asset_maintenance`, `activos_depreciacion` y `depreciacion_acumulada` se siguen creando en toda base nueva, con montos en REAL, y ningún código las lee ni las escribe. Son fuentes paralelas de «valor de activos» y «depreciación» que compiten con `fixed_assets`. `MIGRATION_LOG.md` afirma que `activos_depreciacion` tiene escritor vivo, lo que ya no es cierto. Una base real podría tener datos históricos en ellas que no se ven en ninguna pantalla.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `migrations/m000_base_schema.py:1441,1459,1472,1490,3070` — `CREATE TABLE IF NOT EXISTS` de las cinco tablas (*verificado directamente*); invocadas en `:88`
- `migrations/standalone/060_depreciacion_acumulada.py:9-14` — `depreciacion_acumulada`, REAL
- `migrations/standalone/_cutover_spec_generated.py:15,24,74,149` — aún listadas
- `migrations/MIGRATION_LOG.md:2998` — «Conservadas (escritores operativos vivos)… activos_depreciacion» (*verificado directamente*)
- `migrations/standalone/083_financial_traceability_tables.py:113` vs `backend/infrastructure/db/schema/finance_schema.py:610` — doble definición de `fixed_assets` (REAL vs TEXT), resuelta solo porque la 117 borra la primera (`finance_schema.py:925-946`)

## Impacto
Datos: posible información histórica de equipos y mantenimientos invisible; esquema que duplica la fuente de verdad del valor de activos.

## Objetivo
- Medición sobre una copia de la BD real: filas por tabla.
- Según la medición y la decisión del responsable: migrar los datos a `fixed_assets`/EAM o retirarlos; las tablas dejan de crearse en bases nuevas.
- `MIGRATION_LOG.md` refleja el estado real.

## Alcance
- **Incluye:** Medición, migración de retiro y documentación.
- **No incluye:** Construir la persistencia EAM (SDLC-ASSET-010).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- ASSET-23 (tablas huérfanas identificadas)
- Memoria: `assets` la leía Finanzas en septiembre; hoy ya no (barrido A/D)

## Preguntas abiertas
- Si la copia de la BD real tiene filas en `activos` o `mantenimientos`: ¿se migran al EAM nuevo cuando exista (esperar a SDLC-ASSET-010), se migran a `fixed_assets`, o se archivan en un respaldo y se descartan?
