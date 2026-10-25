# 01 — Auditoría de la arquitectura actual

Clasificación: **REUTILIZAR · EXTENDER · CONSOLIDAR · ADAPTAR · DEPRECAR · CREAR**.

## Capas y composición

| Componente | Ruta real | Estado observado | Clasificación |
|---|---|---|---|
| Dominio (entidades, VOs, políticas) | `backend/domain/<contexto>/` (~40 contextos) | Puro en su mayoría; algunos importan `backend.application.*.permissions` (p. ej. `domain/inventory/policies/scope_policy.py`) | REUTILIZAR |
| Casos de uso / comandos / consultas | `backend/application/<contexto>/`, `backend/application/use_cases/`, `backend/application/queries/` | Extenso; políticas de autorización por contexto (`authorization.py`) | REUTILIZAR |
| Repositorios | `backend/infrastructure/db/repositories/<contexto>/` | SQL `qmark` sobre SQLite; ninguno abstrae dialecto | EXTENDER (adaptador PG por contexto que se replique) |
| Unidad de trabajo | `backend/infrastructure/db/unit_of_work.py` + **23** UoW por contexto | Llaman `commit()/rollback()` sin `BEGIN`; atómicas sólo si la conexión está en modo implícito (ver 06, R-01) | CONSOLIDAR semántica de conexión |
| Conexión | `backend/infrastructure/db/connection.py` (pool hilo-local, **autocommit**, WAL, FK ON) y `backend/bootstrap/steps/database_integrity_step.py` (`sqlite3.connect` implícito, **FK OFF**) | Dos semánticas distintas sobre el mismo archivo | CONSOLIDAR |
| Dialecto | `backend/infrastructure/db/dialect.py`, `database.py` (`DatabaseSettings`, `create_connection_factory`) | Ya contempla `POSTGRESQL`; la fábrica PG lanza `NotImplementedError` | EXTENDER (es el punto de entrada correcto) |
| Contenedor / composición | `backend/bootstrap/` (`CompositionRoot`, `ServiceRegistry`, `ApplicationContext`) y composiciones por módulo en `frontend/desktop/modules/*/composition.py` | Funcional | REUTILIZAR |
| EventBus | `backend/shared/events/event_bus.py` (en memoria, síncrono) + `event_dispatcher.py`, `application_bus.py`; cableado en `backend/bootstrap/wiring/event_wiring.py` | En proceso; integra contextos sobre la misma SQLite | REUTILIZAR (no es transporte de red) |
| Outbox por contexto | ~30 repositorios (`*OutboxRepository`), ~49 tablas `*_outbox` / `*_inbox` | Despachan al bus local (`dispatch_*_outbox`); 0 filas pendientes en la base real salvo `sales_outbox`=1 | REUTILIZAR como **fuente** de replicación |
| Motores de sincronización | Caja `application/cash_register/offline_sync.py` (CASH-19), Inventario `application/inventory/sync/` (INV-22, con `event_ingestor.py`), Mermas `application/losses/offline.py` | Tres implementaciones paralelas, **ninguna con transporte real** (`_MissingCashSyncTransport`, `InMemoryTransport`) | CONSOLIDAR en uno (base: CASH-19) |
| Sincronización heredada | Tablas `sync_outbox`, `sync_inbox`, `sync_state` (`lamport_clock`, `device_id='local'`), `sync_batch_log`, `sync_version_history`, `event_outbox` (m000) | Sin escritores vivos; sólo `frontend/desktop/shell/shutdown/outbox_flusher.py` y la pantalla Offline las tocan | DEPRECAR |
| Contexto «offline» | `backend/domain/offline/`, migración 223, `configuracion/pages/offline_page.py` | Caché de entradas y políticas de expiración; no replica | REUTILIZAR (UI de estado) |
| Autenticación | `backend/application/security/` (login, recuperación), `backend/api/mobile_session.py`, `mobile_credentials.py` | Usuarios locales; credencial móvil verificada contra la base | EXTENDER (credencial de **estación** ante el central) |
| Autorización | `backend/application/security/permission_catalog.py`, `permission_query_service.py`, `principals.py`, verificadores de sesión por contexto | Consolidada en PERM-AUD 968e0bc: un catálogo, `unwired()` fail-closed, concesiones de integración | REUTILIZAR (mismo catálogo en el central) |
| Identidad | `backend/shared/ids.py` (`new_uuid` = UUIDv7, `derived_uuidv7`, `validate_uuidv7`); tablas `installation`, `workstations`, `cash_registers`, `sucursales` | 772 tablas con PK TEXT/UUID; **0 PK enteras** | REUTILIZAR |
| Migraciones | `migrations/engine.py` (lista explícita de **325**), `migrations/standalone/` (**338** archivos), DDL por contexto en `backend/infrastructure/db/schema/*.py` invocado desde migraciones | Funcional e idempotente en su mayoría; 13 archivos sin registrar | REUTILIZAR + EXTENDER con un carril PG (ver 03) |
| API | `backend/api/main.py`, `routers/`, `service_host.py` (FastAPI, `spj_api.exe`) | Rutas BI, móviles de Pedidos/Compras/Logística, sesión móvil; **ninguna de sincronización** | EXTENDER (`/api/v1/sync/*`) |
| WhatsApp | `whatsapp_service/` (raíz del repo), `erp/bridge.py` | Abre el **archivo SQLite del ERP** (`ERP_DB_PATH`); existe modo `ERP_API_URL` | ADAPTAR (vía API central) |
| BI | `backend/application/analytics/`, `forecasting/`, `frontend/desktop/modules/business_intelligence/` | Lee SQLite local; parte lee `inventory_stock` (proyección anterior) | ADAPTAR (consultas corporativas en el central) |
| Web | `frontend/web/delivery`, `frontend/web/logistics` (PWA) | Contra la API de la estación | ADAPTAR |
| Respaldo | `backend/infrastructure/db/sqlite_backup.py` (`SQLiteBackupService`: API de backup, sha256, integrity_check, metadatos) | Funcional | REUTILIZAR |
| Instalador / actualizador | `installer/windows/spj.spec`, `spj_updater.spec`, `spj_setup.iss`, `backend/infrastructure/updater/` (firmado, rollback) | INST-0 construido; CI Windows verde (run 38902999978) | EXTENDER (endpoint central + aprovisionamiento) |
| Perfiles de instalación | `backend/domain/software_distribution/install_profile.py` | Capacidades por estación, bloquea permisos de módulos no instalados | REUTILIZAR |
| Hardware | `backend/infrastructure/hardware/` (tickets, cajón, etiquetas), `scale_gateway.py`, `application/sales/scale_reading_service.py`, `frontend/desktop/modules/sales_pos/scale_monitor.py` | Local a la estación; no se toca | REUTILIZAR |
| Rutas de datos | `backend/shared/app_paths.py` (`AppPaths.database_path`) | Única fuente de la ruta | REUTILIZAR |

## Conclusión de la fase

La arquitectura que se debe **extender** existe y es la correcta:

- casos de uso con políticas de autorización;
- outbox por contexto;
- `DatabaseSettings`/`dialect`;
- API FastAPI;
- `SQLiteBackupService`;
- instalador firmado.

No falta un motor de sincronización: **sobran tres a medio hacer**. La primera tarea de implementación es consolidarlos, no crear un cuarto (ver 05 y 07).
