# Slice 3 — PostgreSQL mínimo del servidor central (ADR-001, ADR-005)

Fecha: 2026-10-25. Migración central **p001**.

## Restricción del entorno

En este equipo no hay PostgreSQL ni capacidad para instalarlo, y la VM de Oracle aún no existe. Por eso:

- Lo verificable sin servidor se prueba aquí: configuración, fábrica de conexiones, contrato del DDL y
  orden del carril con una conexión **simulada**, declarada como tal.
- Lo que exige un PostgreSQL real se prueba en **GitHub Actions**, con un PostgreSQL 16 de servicio
  (trabajo `central-postgres`, sin costo). Ese trabajo **falla si las pruebas se saltan**, para que nunca
  se tome un salto por un éxito.

Nada de este slice se declara probado contra PostgreSQL hasta que ese trabajo pase.

## Qué se construyó

| Pieza | Archivo | Notas |
|---|---|---|
| Conexión | `backend/infrastructure/db/database.py` | Rama PostgreSQL de `create_connection_factory` con psycopg 3, importado sólo en el servidor (detalle abajo) |
| Carril `pg` | `migrations/engine.py` (`PG_MIGRATIONS`, `up_postgresql`) | Mismo contrato que el carril SQLite, más dos garantías (detalle abajo) |
| Esquema central | `migrations/pg/p001_central_replication.py` | `sync_stations`, `sync_inbox`, `sync_aggregate_heads`, `sync_conflicts` |
| Dependencias del servidor | `requirements-server.txt` | FastAPI, uvicorn y `psycopg[binary]`; ruedas para Linux aarch64 (ARM64 de Oracle). Las estaciones Windows no las instalan |
| CI con PostgreSQL real | `.github/workflows/ci-segmented.yml`, trabajo `central-postgres` | PostgreSQL 16 de servicio; falla si las pruebas se saltan |

**Conexión:**

- `autocommit=False`, tiempo límite de conexión y de sentencia, y `application_name`.
- La cadena viene de `SPJ_PG_DSN`, una variable del servidor que vive fuera del repo; **nunca** se configura
  en el cliente Windows.
- La contraseña nunca aparece en `repr` ni en mensajes (`redact_url`).

**Carril `pg`:** además de lo que comparte con el carril SQLite (lista explícita, `run(conn)`, registro en
`schema_migrations`), da dos garantías:

- cada migración corre en su propia transacción y PostgreSQL revierte su DDL completo si falla;
- `pg_advisory_lock` impide que dos procesos migren a la vez.

Sin Alembic (ADR-005).

### Esquema central (p001)

Tipos nativos del §5.2:

- `UUID` para toda identidad, **sin valores por omisión en la base**: los UUIDv7 los genera la capa
  canónica;
- `TIMESTAMPTZ` para instantes, `JSONB` para cargas auditables y `BIGINT` para ordinales;
- ninguna columna autoincremental y ningún `REAL`, `FLOAT` ni `MONEY`.

| Regla del negocio | Dónde la impone la base |
|---|---|
| Un hecho se aplica una sola vez | `sync_inbox.event_id` es PRIMARY KEY; la ingesta usará `ON CONFLICT DO NOTHING` |
| Mismo `event_id` con otro contenido = conflicto | `content_hash` guardado; la comparación es del Slice 4 |
| Detectar huecos de secuencia | `UNIQUE (station_id, sequence_no)` |
| Sólo estaciones registradas envían | FK a `sync_stations`; estado ACTIVE/SUSPENDED/RETIRED y baja con fecha obligatoria |
| Nada falla en silencio | `CHECK`: un hecho no aplicado exige `error_code`; un conflicto resuelto exige resolución, autor y fecha |
| Orden causal por agregado | `sync_aggregate_heads` (última versión aplicada) |

La credencial de estación se guarda como huella (`credential_hash`). Su emisión y verificación son del
Slice 4.

## Evidencia

**Aquí:** `tests/unit/central_pg/test_postgres_lane_contract.py`, 20 pasan.

- La contraseña nunca se ve, y la configuración sale sólo del entorno del servidor.
- Sin psycopg, el error de configuración es claro.
- Las conexiones son transaccionales y tienen límites.
- La conexión SQLite del escritorio no cambió.
- El carril es explícito, ordenado e invocable.
- El DDL no tiene tipos con pérdida ni identidades generadas por el servidor; todo es idempotente y con
  llave UUID.
- Carril con conexión simulada: aplica una sola vez bajo el bloqueo; si una migración falla, se revierte y
  el bloqueo se libera.

**En el CI** (`central-postgres`, PostgreSQL 16): `tests/integration/central_pg/test_central_pg_schema.py`
prueba:

- carril idempotente;
- tipos efectivos (`uuid`, `timestamp with time zone`, `jsonb`, `bigint`);
- `event_id` como clave de idempotencia, incluido `ON CONFLICT DO NOTHING`;
- secuencia única por estación y FK a la estación;
- hecho no aplicado sin motivo, rechazado;
- dinero exacto en JSONB y fechas en UTC;
- baja de estación sin fecha, rechazada;
- un segundo proceso no obtiene el bloqueo de migraciones.

**Resultado en el CI:** el trabajo `central-postgres` de la ejecución 40199145410 (commit `85446537`,
2026-10-25) pasó **en verde** contra PostgreSQL 16. El paso que falla si alguna prueba se salta también
pasó, así que las pruebas de PostgreSQL real **sí corrieron**.

## Pendiente

- **Rol de base con privilegio mínimo** para la API (sólo `SELECT`/`INSERT`/`UPDATE` sobre las tablas de
  sincronización). Crear roles exige superusuario, así que va en la guía de despliegue del servidor
  (Slice 10), no en una migración.
- **Unidad de trabajo para PostgreSQL.** `TransactionalUnitOfWork` usa la semántica de `sqlite3`. La
  ingesta (Slice 4) usará `connection.transaction()` de psycopg, que ya da `SAVEPOINT` anidado.
- **Respaldos** `pg_dump` (ADR-007, Slice 11).
