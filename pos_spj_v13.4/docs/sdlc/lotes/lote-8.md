# Lote 8 — Terminales y sincronización

Rama `fix/lote-8`, salida de `sdlc/sdlc-arq-term-002` (47d0a83f) más las aprobaciones del 2026-11-05
(0b3bd2fe). Comparada contra `claude/erp-financial-bounded-context-uqxz6b`.

| Ítem | Estado | Commit |
|---|---|---|
| SDLC-ARQ-TERM-002 | **LISTO** (construido en `sdlc/sdlc-arq-term-002`, verificado aquí) | 47d0a83f y anteriores |
| SDLC-SYNC-001 | **LISTO**, con lo de PostgreSQL real sin verificar aquí | bf331f72 |
| SDLC-SYNC-002 | **LISTO**, con lo de PostgreSQL real sin verificar aquí | f6e725f2 |
| SDLC-ARQ-TERM-001 | **BLOQUEADO** en parte: identidad y sesión hechas; retirar los registros duplicados, no | c9151d46 |
| SDLC-ARQ-SYNC-001 | **ESPERA**: depende de SDLC-SYNC-003 (y de la parte pendiente de TERM-001) | — |
| SDLC-SYNC-003 | Saltado por encargo: intent en borrador | — |

## SDLC-ARQ-TERM-002 — verificado, sin defectos

Se corrieron sus 75 pruebas y se revisó el diff de código contra la rama base: permiso en backend con
falla cerrada, guardas dentro de la unidad de trabajo, auditoría, sesión de reparación sin módulos
operativos y sembrado de la 357 sólo a `system_owner` y `admin`. No se cambió nada.

Observación, no defecto: `central_enrollment_active` sólo mira `status='ENROLLED'`, como dice el spec
(R2). Una estación `SUSPENDED` o `REVOKED` por el central podría re-anclarse con permiso local. Hoy
nadie escribe `device_enrollment`, así que no ocurre. Conviene revisarlo cuando exista el enrolamiento
(SDLC-ARQ-TERM-004/005).

## SDLC-SYNC-001 — el carril PostgreSQL aplica p006

- **Cambio:** `p006` entra en `PG_MIGRATIONS` y `354_device_enrollment` en `MIGRATIONS` (decisión del
  responsable: es del mismo slice).
- **Hallazgo no previsto en el intent:** registrar p006 tal cual rompía el contrato del carril, porque
  `central_device_events.id` era `BIGSERIAL` y el carril prohíbe identidades del servidor. Como p006
  nunca corrió en ningún central, se corrigió en sitio a `UUID` y `add_device_event` genera el id.
- **Guardia:** `tests/unit/central_pg/test_postgres_lane_contract.py` falla si un `migrations/pg/p*.py`
  queda sin registrar o si el repositorio selecciona una columna que el carril no crea. Está en el job
  `central-postgres`.
- **Prueba nueva con PostgreSQL real:** `test_empty_central_accepts_a_station_and_a_device_enrollment`
  en `tests/integration/central_pg/test_central_pg_schema.py`.
- **No verificado:** esa prueba no corre aquí (no hay PostgreSQL ni `psycopg`). Queda para el job
  `central-postgres`. Tampoco se probó `/api/v1/sync/events` contra un PostgreSQL recién migrado.

## SDLC-SYNC-002 — un conflicto no se vuelve SYNCED

- **Causa:** la ingesta respondía DUPLICATE por huella sin mirar el estado guardado. No hacía falta
  ninguna acción humana: bastaba perder un acuse para que la estación reintentara y marcara SYNCED.
- **Cambio:** con la misma huella, DUPLICATE sólo si el hecho quedó APPLIED; si no, CONFLICT con su
  código original y sin abrir otro conflicto (`fact_status` en el puerto y en PostgreSQL).
- **Resolución (decisión del responsable: estación, en Configuración → Offline):** tarjeta «Conflictos
  de sincronización» con `RETRY_LOCAL` y `ACCEPT_REMOTE`, que son las dos salidas que Caja ya tenía.
  Exige `CONFIGURACION.offline.gestionar` en backend y motivo, y deja rastro en `audit_logs`
  (`sincronizacion.conflicto.resolver`) en la misma transacción.
- **Pruebas:** `tests/unit/central_sync/test_central_ingestion.py` (reenvío y duplicado real),
  `tests/integration/sync/test_replication_conflicts.py` (estación + ingesta, acuse perdido, permiso,
  motivo, doble resolución), `tests/unit/test_offline_page.py` (pantalla por la fábrica real).
- **No verificado:** `test_resending_a_stored_conflict_answers_conflict` en
  `tests/integration/central_pg/test_central_ingestion_pg.py` necesita PostgreSQL real.

Para revisión del responsable:

- `ACCEPT_REMOTE` deja el sobre en SYNCED y el hecho **no llega a los libros centrales**. Es explícito y
  queda auditado, pero es dinero que sale del consolidado; la pantalla lo advierte en el título del
  diálogo. No hay política por tipo de agregado: el intent la deja fuera.
- `RETRY_LOCAL` sobre un hecho guardado en conflicto siempre vuelve a CONFLICT: en el central nadie
  resuelve conflictos todavía (SDLC-ARQ-SYNC-002).
- Los conflictos de Caja se ven en dos pantallas: Caja → Sincronización y Configuración → Offline. Se
  dejó así por la respuesta del responsable, que pide Configuración, aunque choca con la regla de no
  duplicar módulos en Configuración. Por Configuración no se escribe `CASH_SYNC_CONFLICT_RESOLVED` ni
  se valida el alcance por sucursal de Caja. Decidir si Caja debe quedar sólo como consulta.

## SDLC-ARQ-TERM-001 — identidad hecha, retiro pendiente

**Hecho (c9151d46):**

- `workstations` como fuente canónica, con `schema_version` y `protocol_version` nuevas.
- `configuraciones.terminal_instalacion_id` guarda el UUIDv7. El hostname queda como dato descriptivo
  en `device_identifier`.
- La sesión nace con ese id desde el login. `LegacySessionAdapter.workstation_id` deja de ser `None`,
  y por eso las ventas nuevas ya guardan `sales.workstation_id`.
- `software_station_settings` usa el id en vez del hostname.
- La fila se crea o actualiza al iniciar sesión con ancla. Sin ancla sólo hay id.
- Prueba: `tests/integration/configuracion/test_terminal_identity.py` (16 pruebas, incluye renombrar el
  host).

**Consecuencias de que el id deje de ser `None`, ya cubiertas:**

| Consumidor | Qué habría pasado | Qué se hizo |
|---|---|---|
| Báscula | El POS se quedaba sin báscula si la terminal no tenía asignación | Sin asignación rige la de la sucursal |
| Ventas suspendidas | Las suspendidas sin terminal dejaban de verse | Se listan y se cuentan en cualquier terminal |
| Pantalla de cliente | Se creaba otra pantalla, porque la existente cuelga de otra fila | La 392 adopta la única fila activa sin máquina |
| Barra de estado | Mostraba un UUID completo | Muestra `TERM-XXXXXXXX` |

**No hecho, y por qué queda BLOQUEADO:** la decisión del 2026-11-02 pide borrar las demás tablas y sus
migraciones. No se hizo, y el objetivo «caja usa ese id» sigue sin cumplirse.

1. **`pos_terminals`:** es padre por FK de `cash_shifts` y `cash_shift_assignments`, y SQLite no permite
   FK hacia una vista, así que retirarla exige reconstruir esas dos tablas financieras con datos reales.
   Toca además 8 puntos de SQL en backend y 31 archivos de prueba. Es T0, no tiene spec, y aquí no se
   pudo probar sobre una copia de la base real. Además, `workstations` no tiene `register_id`.
2. **`device_enrollment`:** dos decisiones se contradicen. La respuesta de SDLC-SYNC-001 (2026-11-05) la
   conserva como parte del slice, y SDLC-ARQ-TERM-002 R2 la usa; la de TERM-001 (2026-11-02) dice borrar
   las demás.
3. **`software_station_settings`:** no sólo guarda identidad, también el canal y la ventana de
   mantenimiento. Se le quitó el hostname, pero no se borró para no perder esa función.
4. **`sync_stations` y `replication_stations`:** son del central y del motor de replicación; el intent
   deja el enrolamiento fuera (TERM-004/005).

**Preguntas para el responsable:**

- ¿Se aprueba un ítem aparte, con spec, para reconstruir `cash_shifts` y `cash_shift_assignments` y
  apuntarlas a `workstations`, con prueba sobre copia de la base real? ¿La relación caja-terminal pasa a
  `workstations.register_id`?
- ¿`device_enrollment` se conserva como vinculación con el central, y «borrar las demás» sólo aplica a
  los registros locales de identidad?
- `sales.workstation_id` sigue siendo nullable: las filas viejas no tienen terminal. ¿Se exige NOT NULL
  para ventas nuevas?

**Riesgos que quedan:**

- Copiar la base a otra máquina clona la identidad. Protegerla es SDLC-ARQ-TERM-005.
- Con varias filas activas sin máquina no se adopta ninguna: nace una fila nueva y, si había pantalla de
  cliente, se crea otra con valores por omisión.
- Una terminal BLOCKED ahora hace fallar báscula y pantalla de cliente, que validan el estado. Validarla
  al entrar es SDLC-ARQ-TERM-003.
- La preferencia del menú lateral se reinicia una vez, porque su llave incluye el id de la terminal.

## Migraciones

| Migración | Qué hace | Probada en |
|---|---|---|
| `p006` (registrada) | Equipos en el central; `central_device_events.id` pasa a `UUID` | Contrato del carril; PostgreSQL real **sin verificar** |
| `354` (registrada) | Tabla `device_enrollment`, vacía | Prueba de registro |
| `392` (nueva) | Identidad de terminal y columnas de versión | Bases en memoria, idempotente |

No se usaron 393–395. Ninguna se probó sobre una copia de la base real.

## Resultados de pruebas

RESULTADOS_PENDIENTES

## Fallos preexistentes

- `tests/test_migration_audit.py` busca `scripts/audit_migrations.py` en la raíz del repo, y el archivo
  vive en `pos_spj_v13.4/scripts/`. No lo causa este lote. La línea base del 2026-10-28 no lo registra
  porque corre fuera de sus segmentos (`tests/unit`, `tests/integration`, `tests/architecture`).
