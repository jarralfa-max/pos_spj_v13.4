# 02 — Inventario de dependencias de SQLite

Conteos por ocurrencias en `.py` (medidos con `grep -E`, 2026-10-23). «backend» = `pos_spj_v13.4/backend`;
«WA» = `whatsapp_service/` en la raíz.

## Patrones del §3.2

| Patrón | backend | frontend | migrations | WA | Comentario para PostgreSQL |
|---|---:|---:|---:|---:|---|
| `sqlite3.` | 148 | 1 | 169 | 92 | Aislar en infraestructura; el central no usa `sqlite3` |
| `PRAGMA` | 53 | 0 | 159 | 10 | `table_info` (25 en 19 archivos de backend) → `information_schema` |
| `sqlite_master` | 83 (72 archivos) | 0 | 121 | 8 | Comprobaciones «¿existe la tabla?» en repositorios; en PG la tabla existe por contrato de migración |
| `lastrowid` | 1 | 0 | 1 | 8 | WA aún depende de ids generados por la base; el backend ya no |
| `AUTOINCREMENT` | 6 | 0 | 2 | 6 | En la base real: **0 tablas** con AUTOINCREMENT y **0 PK enteras** |
| `INSERT OR IGNORE` | 34 (30 archivos) | 0 | 107 | 1 | → `ON CONFLICT DO NOTHING` |
| `INSERT OR REPLACE` | 1 | 0 | 1 | 0 | Semántica distinta de un upsert PG (borra y reinserta): revisar caso por caso |
| `ON CONFLICT` | 188 | 0 | 7 | 17 | Compatible (SQLite ≥ 3.24 y PG usan la misma sintaxis) |
| `BEGIN IMMEDIATE` | 1 | 0 | 2 | 0 | Bloqueo de escritor SQLite; sin equivalente directo |
| `row_factory` | 12 | 0 | 1 | 9 | Repositorios leen por nombre de columna → portable con `dict_row` |
| `executemany` | 4 | 0 | 2 | 0 | Portable |
| `ATTACH DATABASE` | 0 | 0 | 0 | 0 | — |
| `datetime('now')` | 81 (20 archivos) | 0 | 357 | 30 | Default de columnas y SQL; en PG `now()` / `timestamptz` |
| `strftime(` | 23 | 7 | 4 | 2 | Formatos de fecha en SQL → mover a Python o `to_char` |
| `\|\|` (concatenación) | 58 (11 archivos) | — | — | — | Compatible |
| `REAL` (texto) | 80 | 33 | 710 | 22 | Ver 03: 203 columnas de dinero/cantidad en REAL en la base real |
| `.commit()` | 282 | **0** | 319 | 78 | La interfaz no confirma transacciones (correcto) |
| `.rollback()` | 60 | 0 | 9 | 0 | |
| `CREATE TABLE` | 495 | **0** | 527 | 27 | El DDL de backend vive en `infrastructure/db/schema/*.py` y se invoca desde migraciones |

**Sin hallazgos** en: SQL ejecutado desde widgets (0 `execute("SELECT…` en `frontend/`) y `ATTACH DATABASE`.

## Conexiones y transacciones (hallazgo crítico de diseño)

| Ruta | Cómo abre | Transacción | FK | Quién la usa |
|---|---|---|---|---|
| `backend/bootstrap/steps/database_integrity_step.py:28` | `sqlite3.connect(path)` | Implícita (Python abre `BEGIN` al primer DML) | **OFF** (`PRAGMA foreign_keys` = 0, medido) | La ventana del escritorio (`bootstrap.context.conn` → `frontend/desktop/app.py:454`) |
| `backend/infrastructure/db/connection.py:93` `_new_connection` | `isolation_level=None`, WAL, `foreign_keys=ON`, `check_same_thread=False` | **Autocommit**: sin `BEGIN` explícito cada sentencia confirma | ON | Pool hilo-local `get_connection()`; `DatabaseModuleProvider` |
| `backend/infrastructure/db/database.py` `create_connection_factory` | `sqlite3.connect` | Implícita | ON en `api/service_host.py:137` | API FastAPI (`spj_api.exe`) |

**Prueba ejecutada** (copia de la base real): dentro de `FinanceUnitOfWork`, `InventoryUnitOfWork` y
`SalesUnitOfWork` se inserta una fila y se lanza una excepción.

- Con la conexión del escritorio, el rollback deshace las tres filas: las UoW son atómicas.
- Con `_new_connection` (autocommit), **las tres filas sobreviven**: las mismas UoW no son atómicas.

Las 23 unidades de trabajo dependen de la semántica de la conexión que reciben y ninguna abre su propia
transacción. Para el Outbox transaccional (§6.2) es bloqueante: hay que fijar UNA semántica (ver 06, R-01).

## Hilos

`connection.py` usa almacenamiento hilo-local (`_tls`) con `check_same_thread=False` y un `RLock` por
conexión en `transaction()`. La API comparte una conexión entre hilos serializando el acceso
(`service_host.py`). Un trabajador de sincronización en segundo plano debe usar **su propia conexión**, no
la de la interfaz.

## WAL y copias de archivo

- La base está en WAL (medido). `sqlite_backup.py` usa la API de backup de SQLite, verifica
  `integrity_check` y calcula sha256 (correcto).
- `database_relocation.py` también usa la API de backup.
- No se encontraron copias con `shutil.copy` del archivo vivo en código de producción.
