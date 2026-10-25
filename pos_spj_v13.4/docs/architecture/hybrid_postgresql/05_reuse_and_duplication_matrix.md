# 05 — Matriz de reutilización y duplicación

Toda creación lleva evidencia de que no existe un equivalente.

## Reutilización por necesidad del modelo híbrido

| Necesidad (prompt) | Existe | Decisión | Justificación |
|---|---|---|---|
| Fábrica de conexión por dialecto | `backend/infrastructure/db/database.py` (`DatabaseSettings`, `create_connection_factory` con rama PG que lanza `NotImplementedError`) + `dialect.py` | **EXTENDER** | Ya es el punto de entrada de la API; implementar la rama PG (psycopg 3) |
| Unidad de trabajo | `DbApiUnitOfWork` + 23 UoW por contexto | **EXTENDER** | Las UoW reciben una conexión; con un adaptador PG que respete el contrato DB-API funcionan igual. Requiere cerrar R-01 y R-02 |
| Repositorios | 1 por agregado, SQL `qmark` | **ADAPTAR** sólo los de contextos replicados | Traducción `?`→`%s` y funciones de fecha en un adaptador; no se duplica la clase |
| Outbox transaccional local | ~30 outbox por contexto que se escriben en la misma transacción que el agregado | **REUTILIZAR** como fuente | Ya cumplen «misma transacción» (con la conexión implícita del escritorio) |
| Motor de replicación (envío, reintento, ACK, cursor, dead-letter) | **Tres** parciales: Caja CASH-19 (`offline_sync.py`, sobres, secuencia, ACK, conflictos, backoff exponencial), Inventario INV-22 (`sync/outbox_dispatcher.py`, `event_ingestor.py`, cursor), Mermas (`losses/offline.py`) | **CONSOLIDAR** en uno, generalizando CASH-19 | Crear un cuarto motor es justo lo que prohíbe §17. CASH-19 es el más completo (lotes, estados, conflictos visibles) |
| Inbox / ingesta central | `inventory/sync/event_ingestor.py` (dedup por evento) | **EXTENDER** a todo contexto | Es el único ingestor existente |
| Transporte HTTP | Ninguno (`_MissingCashSyncTransport`, `InMemoryTransport`) | **CREAR** un transporte HTTPS | Ningún equivalente; `httpx` ya es dependencia (`requirements.txt`) |
| API central | `backend/api/main.py` + `routers/` (FastAPI) | **EXTENDER** con `/api/v1/sync/*` | Ya empaquetada como `spj_api.exe`; mismas dependencias |
| Autenticación de usuarios | `backend/application/security/` | **REUTILIZAR** | Mismo catálogo de usuarios y contraseñas (bcrypt) |
| Autenticación de estación ante el central | `backend/api/mobile_credentials.py` (credencial verificada contra la base) y tablas `installation`, `workstations`, `cash_sync_devices` | **EXTENDER** | Hay identidad de estación; falta una credencial de dispositivo emitida por el central y revocable |
| Autorización | Catálogo único + verificadores de sesión + concesiones de integración (PERM-AUD 968e0bc) | **REUTILIZAR** en el central | El central revalida con el mismo catálogo; nunca confía en permisos enviados por el cliente |
| Identidad UUIDv7 | `backend/shared/ids.py` | **REUTILIZAR** | 0 PK enteras; mapeo directo a `uuid` |
| Decimal | Política vigente: decimal en `TEXT` en SQLite y `Decimal` en Python | **REUTILIZAR** → `NUMERIC(p,s)` | Hay que fijar `p,s` por dominio en el ADR de tipos |
| Migraciones | `migrations/engine.py` | **EXTENDER** con un carril PG | Alembic no se justifica: el motor actual ya es explícito, idempotente y auditado |
| Respaldo SQLite | `SQLiteBackupService` | **REUTILIZAR** | API de backup, sha256, integridad, metadatos |
| Respaldo PostgreSQL | Ninguno | **CREAR** (scripts `pg_dump`/`pg_restore` + verificación) | Sin equivalente |
| Instalador / actualizador | `installer/windows/*`, `backend/infrastructure/updater/` | **EXTENDER** | Agregar endpoint central, credencial de aprovisionamiento y diagnóstico de conectividad |
| Estado de sincronización en la UI | Pantalla Offline (`configuracion/pages/offline_page.py`), `cash_sync_devices.sync_status` | **EXTENDER** | Ya hay dónde mostrarlo |
| Conflictos visibles | `sync_conflicts` (m000), `customer_sync_conflicts`, `crm_sync_conflicts`, `loss_sync_conflicts` | **CONSOLIDAR** | Cuatro tablas de conflictos; una vista operativa común |

## Duplicaciones a consolidar (no a reproducir en el central)

| Duplicado | Ubicaciones | Acción |
|---|---|---|
| Motores de sincronización | Caja, Inventario, Mermas | Uno solo |
| Tablas de conflictos | 4 | Una tabla común (o vista) con contexto |
| Semántica de conexión | `_new_connection` (autocommit) vs. `sqlite3.connect` implícito | Una sola (R-01) |
| Modelo de ventas | `ventas` (heredado) vs. `sales` (canónico) | Replicar sólo `sales` |
| Proyección de inventario | `inventory_stock`, `inventario_actual` vs. `inventory_balances` | Replicar el ledger; BI lee del canónico |
| Sincronización heredada | `sync_outbox`, `sync_inbox`, `sync_state` (`lamport_clock`), `sync_batch_log`, `sync_version_history`, `event_outbox` | DEPRECAR (sin escritores vivos) |
| Acceso de WhatsApp al ERP | Archivo SQLite directo vs. `ERP_API_URL` | Sólo API |

## Lo que NO se crea

- Un segundo ERP en el servidor. El central ejecuta los **mismos** casos de uso y dominios con
  repositorios PG.
- Un segundo EventBus.
- Un segundo catálogo de permisos.
- Una segunda generación de ids.
