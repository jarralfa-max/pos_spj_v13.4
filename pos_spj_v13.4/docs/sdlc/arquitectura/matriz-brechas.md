# Matriz de brechas — `requisitos-arquitectura.md` §2–§15

- **Fecha:** 2026-10-29 · **Commit base:** `cebedb5` · **Rama:** `claude/erp-financial-bounded-context-uqxz6b`
- **Método:** `/sdlc-plan arquitectura` (modo C). Cinco subagentes de lectura en paralelo, agrupados por sección (§2+§10, §3+§4+§14, §5+§6+§7+§11, §8+§9+§12, §13+§15). Cada fila lleva ruta:línea leída en el código. Las afirmaciones que sostienen ítems P0 se volvieron a leer al consolidar. Un módulo, una abstracción o un documento **no** cuentan como implementación.
- **Papel de este documento:** cumple el entregable de Fase 1 que el documento ubica en `docs/spj/auditoria/matriz-hallazgos.md` (§1, §16). Por la regla del comando (`/sdlc-plan` sólo escribe en `docs/sdlc/`) vive aquí; ver pregunta abierta en `BACKLOG.md`.
- **Rutas** relativas a `pos_spj_v13.4/`.
- **Limitación de la evidencia de PostgreSQL:** las pruebas `tests/integration/central_pg/*` se saltan sin `SPJ_TEST_PG_DSN` y `psycopg` (no disponibles en esta sesión). En CI corren contra postgres:16 y el job falla si hay SKIPPED (`../.github/workflows/ci-segmented.yml:70-104`). Aquí no se vio el resultado de CI, así que todo lo PG se marca como **no probado en esta sesión**.

Estados: `implementado y probado` · `parcial` · `documentado no implementado` · `defectuoso` · `duplicado` · `ausente`.

## Resumen

| Sección | Requisitos | Implementado y probado | Brechas → ítems |
|---|---|---|---|
| §2 Arquitectura híbrida | 6 | 2 | HYB-001, HYB-003, HYB-004, SYNC-001 (existente) |
| §3 Usuarios, roles, permisos | 8 | 2 | PERM-001…006 |
| §4 Ámbitos | 5 | 0 | PERM-003, SCOPE-001, TERM-001, BI-001 (existente) |
| §5 Instalación y visibilidad | 4 | 1 | TERM-001, TERM-002, TERM-006 |
| §6 Login entre sucursales | 7 | 2 | TERM-002…005, PERM-004, AUD-001 |
| §7 Varios usuarios | 4 | 1 | SESS-001…003, AUD-002 |
| §8 Caja y turno compartidos | 8 | 1 | SHIFT-001…004, HYB-001 |
| §9 Offline y servicio local | 3 | 0 | HYB-001, HYB-002 |
| §10 Sync, FastAPI, PostgreSQL | 6 | 0 | SYNC-001…004 (ARQ), IDEM-001, SYNC-001…005 y SEC-003/005 (existentes) |
| §11 Auth offline | 3 | 0 | OFF-001, OFF-002, HYB-002, ARQ-SYNC-003 |
| §12 Duplicados y concurrencia | 4 | 0 | IDEM-001…005, SHIFT-004 |
| §13 Instalación y actualización | 6 | 0 (1 en flujo principal) | ARQ-INST-001…003, INST-001…003 (existentes) |
| §14 Seguridad y auditoría | 3 | 0 | AUD-001…003, TERM-002 |
| §15 Pruebas de aceptación | 14 | 2 | TEST-001 + la prueba de cada ítem |

Los IDs abreviados se refieren a `SDLC-ARQ-<…>`. Los de la columna con "(existente)" son ítems del triage 2026-10-28 y se enlazan, no se duplican.

## §2 Arquitectura objetivo

| § | Requisito | Estado | Evidencia | Prueba que lo cubre | Ítem |
|---|---|---|---|---|---|
| 2.A | Una app de escritorio, módulos condicionados por permisos | implementado y probado | `backend/bootstrap/permission_evaluator.py:22-35`; `frontend/desktop/shell/router/desktop_router.py:136-162`; `installer/windows/spj_setup.iss:93-112` | `tests/unit/bootstrap/test_permission_evaluator.py`; `tests/integration/software_distribution/test_profiles_and_schema_gate.py` | — (ver SESS-001 por permisos en vivo) |
| 2.B | SQLite local + cola de salida persistente | implementado y probado | `migrations/standalone/350_replication_engine.py:41-90`; `backend/application/sync/replication_outbox.py:99-258` | `tests/integration/sync/test_replication_outbox.py` (15) | SDLC-SYNC-004/005 (existentes) |
| 2.C | Servicio local de sucursal que coordina caja/turno | documentado no implementado | No existe; `backend/api/service_host.py:1-31` es la API móvil de Logística; decisión contraria D1 en `docs/architecture/enterprise_org/00_phase0_audit.md:147` | ninguna | ARQ-HYB-001 |
| 2.D | API central FastAPI + PostgreSQL | parcial | `backend/api/central_app.py:143-186`; carril PG `migrations/engine.py:465-481` sin p006 | `tests/unit/central_sync/*`; `tests/integration/central_pg/*` (no probado en esta sesión) | SDLC-SYNC-001 |
| 2.E | Clientes nunca directo a PostgreSQL | parcial (cumple por convención) | psycopg sólo en `central_app.py`, `backend/infrastructure/central/sync_inbox_repository.py`, `backend/infrastructure/db/database.py:28,49-60` | ninguna guardia | ARQ-HYB-004 |
| 2.F | TLS, auth servicio a servicio, config protegida, respaldos, observabilidad | parcial | TLS estación `backend/infrastructure/sync/http_transport.py:41-47,77`; firma Ed25519 `backend/shared/security/device_signature.py:96-116`; secretos `backend/security/secrets/*`; sin artefactos de despliegue central, sin `pg_dump`, `/health` sin BD (`central_app.py:155-157`) | `tests/integration/central_sync/test_sync_api_end_to_end.py:161`; firma/dispositivos: ninguna | ARQ-HYB-003, ARQ-TERM-004 |

## §3 Usuarios, roles y permisos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 3.1 | Separar identidad, sesión, roles, permisos, asignaciones, ámbito, terminal, recurso | parcial | Tablas en `migrations/m000_base_schema.py:175,192,206,215`, `353_user_role_assignments.py:35`, `351_organizational_structure.py:51`; sesión sólo en memoria (`frontend/desktop/shell/desktop_shell_authentication_composition.py:85`); terminal en 4-5 lugares | `tests/integration/organization/*` | ARQ-TERM-001, ARQ-SESS-002 |
| 3.2 | El nombre del rol no concede privilegios | defectuoso | `backend/security/permissions/principals.py:24-30`; `legacy_session_adapter.py:158-162` | `tests/architecture/test_customers_crm_permissions_are_not_role_names.py` (parcial) | ARQ-PERM-004 |
| 3.3 | Varios roles y asignaciones por usuario | implementado y probado | `backend/domain/organization/role_assignment.py`; `backend/application/security/access_scope.py:68-97` | `tests/integration/security/test_contextual_permissions.py` (14) | — |
| 3.4 | Configurable por rol y por usuario con precedencia | implementado y probado | ROL < USUARIO < SUCURSAL, gana el más específico: `backend/application/security/permission_query_service.py:3-13,38-42,91-99` | `tests/integration/security/test_permissions_audit_968e0bc.py:408-540` | — (ratificar política: pregunta abierta) |
| 3.5 | Módulo, acción, recurso, ámbito, condiciones | parcial | `backend/security/permissions/codes.py:51-104` (cadena plana) | ninguna | ARQ-PERM-005 |
| 3.6 | Autorización en backend en cada operación | parcial | Falla cerrado sin política (`backend/application/security/unwired_policy.py`); Configuración sólo en presentador (`frontend/desktop/modules/configuracion/configuracion_routes.py:230-300`) | `tests/unit/configuracion/test_configuracion_presenter_authorization.py` (presentador) | ARQ-PERM-001, SDLC-SEC-002 |
| 3.7 | Mínimo privilegio, denegación por defecto, auditoría, alcance | defectuoso | Denegación por defecto OK (`permission_query_service.py:79-85`); escalada por alcance (`role_assignment_service.py:133-157`); dos resolvedores; transferencias pasa sin sucursal (`transfers/session_scope_checker.py:50-52`) | `test_contextual_permissions.py:274` (sólo permisos) | ARQ-PERM-002, ARQ-PERM-003 |
| 3.8 | Matriz de permisos de perfiles de referencia | ausente | Roles sembrados `m000_base_schema.py:3174-3181` | matrices por módulo en `tests/unit/*/test_*_role_matrix.py` | ARQ-PERM-006 |

## §4 Ámbitos organizacionales

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 4.1 | Ámbitos según entidades reales | parcial / duplicado | `backend/domain/organization/org_unit.py:34-41`; `cash_registers`/`cash_drawers` en 175; legacy `cajas`, `turnos_caja`, `turno_actual` aún creados (`m000_base_schema.py:820-890`); almacén como org unit y como `warehouses` | `tests/unit/organization/*` | ARQ-SCOPE-001, ARQ-SHIFT-001 |
| 4.2 | Terminal POS asignada persistentemente; ventas conservan ámbito | parcial | `pos_terminals` no ligada a equipo físico (`backend/infrastructure/desktop/cash_operational_context.py:76-85`); `sales.workstation_id` nullable (`backend/infrastructure/db/schema/sales_schema.py:67-68`) | `tests/integration/cash_register/test_devices_page_only_offers_its_own_branch.py` | ARQ-TERM-001 |
| 4.3 | Logística transversal sin sucursal artificial | parcial | `stock_transfers` con origen/destino (`transfers_schema.py:24-35`), pero sesión siempre anclada | `tests/integration/transfers/test_transfer_full_cycle_32cfbf.py` (con `for_tests`) | ARQ-SCOPE-001 |
| 4.4 | Almacén y producción separados de sucursal | parcial | `warehouses.branch_id NOT NULL` (`inventory_schema.py:84`); sitios reflejados en `sucursales` (`org_unit.py:7-12`) | `tests/integration/meat_processing/test_processing_never_uses_branch_as_location.py` | ARQ-SCOPE-001 |
| 4.5 | Consultas globales/segmentadas dentro de permisos | parcial | `backend/application/security/branch_scope_query_service.py:1-11` en la mayoría; Finanzas sin `can_access_branch` (`backend/application/finance/authorization.py:39-55`); BI | `tests/integration/security/test_branch_scope_query_service.py` | SDLC-BI-001, SDLC-SEC-003, ARQ-PERM-003 |

## §5 Instalación y visibilidad de módulos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 5.1 | Módulo instalado nunca concede acceso (UI y API) | implementado y probado en UI; parcial en API | `frontend/desktop/shell/sidebar/sidebar_resolver.py:63-72`; router; API móvil sin compuerta de capacidad (`backend/api/mobile_credentials.py:42`); default `everything` (`backend/bootstrap/application_context.py:339`) | `tests/integration/software_distribution/test_profiles_and_schema_gate.py:27,40`; API: ninguna | ARQ-TERM-006, ARQ-SESS-001 |
| 5.2 | Perfiles de despliegue POS / administrativa / servicio local / central | parcial | `backend/domain/software_distribution/install_profile.py:33-37` (capacidades) | `tests/unit/software_distribution/test_domain_policies.py` | ARQ-TERM-006 |
| 5.3 | Terminal con id persistente, tipo, ámbito, estado, versiones | duplicado | `workstations`, `pos_terminals`, `device_enrollment` (354 sin registrar), `software_station_settings` por hostname, `sync_stations`; sesión usa hostname (`backend/bootstrap/application_context_builder.py:112`) | ninguna | ARQ-TERM-001 |
| 5.4 | Sucursal del POS no cambia desde login ni por edición local no autorizada | defectuoso | `backend/application/use_cases/set_installation_branch_use_case.py:22-28` (sin permiso ni auditoría); ancla en `configuraciones` | `tests/unit/test_empresa_page_installation_branch.py` (UI); `tests/test_installation_branch_resolution.py` roto | ARQ-TERM-002, SDLC-SET-001 |

## §6 Login y acceso entre sucursales

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 6.1 | Login valida identidad, cuenta, asignaciones, permisos, dispositivo, ámbito | parcial | Identidad/bloqueo `backend/security/authentication/authenticate_user_use_case.py:87-99`; sitio `application_context_builder.py:81-87`; dispositivo: nunca | `tests/integration/bootstrap/test_application_context_builder.py` | ARQ-TERM-003 |
| 6.2 | Usuario de A en POS de B sin asignación → denegado con motivo | implementado y probado | `backend/bootstrap/application_context_errors.py:10-19`; `frontend/desktop/auth/authentication_coordinator.py:87-98` | `test_contextual_permissions.py:198`; `tests/ui/test_authentication_coordinator.py:183` | ARQ-AUD-001 (no se audita) |
| 6.3 | Usuario de A y B → sólo lo permitido en el ámbito activo | implementado y probado | `access_scope.py:98-104`; `application_context_builder.py:85-87` | `test_contextual_permissions.py:134-166,188` | — |
| 6.4 | Cuenta corporativa no obtiene operación POS automáticamente | defectuoso | `access_scope.py:42-45,71-72,86-89`; `permission_evaluator.py:33-34` | `test_contextual_permissions.py:204` fija el comportamiento contrario | ARQ-PERM-004 |
| 6.5 | Nunca cambiar sucursal en silencio al iniciar sesión | parcial | Sin selector; sin ancla usa sucursal propia (`application_context_builder.py:126-129`) | `test_contextual_permissions.py:188` | ARQ-TERM-002 |
| 6.6 | Registrar/suspender/revocar/reasignar con autorización, auditoría y pendientes | parcial | Central: `backend/application/sync/device_provisioning.py:173-176,352-396`; duplicado `station_admin.py:83-100`; actor por cabecera no firmada (`backend/api/routers/devices.py:75`) | ninguna | ARQ-TERM-004 |
| 6.7 | Terminal nueva/suspendida no opera | parcial (sólo central) | `device_provisioning.py:168-170`; escritorio nunca consulta | `test_sync_api_end_to_end.py` (lado sync) | ARQ-TERM-003, ARQ-TERM-005 |

## §7 Varios usuarios en una máquina

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 7.1 | Logins secuenciales con sesión propia; sin sesión global | implementado y probado (parcial en prueba) | Contexto inmutable por login (`application_context.py:312`); adaptador por ventana (`frontend/desktop/app.py:500-503`) | `tests/unit/shell/test_desktop_logout_transition.py` (mocks); A→B integración: ninguna | ARQ-SESS-001 |
| 7.2 | Logout limpia, no cierra caja; bloqueo de pantalla | parcial | Logout `frontend/desktop/app.py:303-330`; sin bloqueo ni TTL | `tests/unit/shell/test_authentication_logout.py` | ARQ-SESS-002 |
| 7.3 | Borradores aislados; transferencia explícita con permiso y auditoría | defectuoso | `backend/application/sales/use_cases/lifecycle_use_cases.py:90-94` (reanudación ajena por defecto) | `tests/unit/test_sales_suspension.py` (banderas) | ARQ-SESS-003 |
| 7.4 | Cada acción registra actor, terminal, ámbito, recurso, fecha, resultado, operación | duplicado | Tres tablas de auditoría; escritor canónico sin terminal ni resultado (`backend/infrastructure/db/repositories/settings/audit_log_repository.py:75-84`) | `tests/integration/shared/test_audit_trail.py` | ARQ-AUD-002 |

## §8 Cajas y turnos compartidos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 8.1 | Gerente en otra terminal consulta el mismo turno | ausente (entre terminales); parcial (misma base) | `cash_operational_context.py:47-65,122-132` filtra por usuario | `tests/integration/cash_register/test_cash_audit_968e0bc.py:138-168` (misma base) | ARQ-SHIFT-002, ARQ-HYB-001 |
| 8.2 | Fuente canónica única del turno activo | duplicado | ~12 resolvedores: `backend/infrastructure/db/repositories/cash_register/repositories.py:63,72,82`; caché `cash_operational_context.py:47-65`; estados copiados `overview_query_service.py:163,220` | `tests/architecture/test_cash_operational_context_resolver.py` (no compara fuentes) | ARQ-SHIFT-001 |
| 8.3 | Permisos separados de caja | parcial | `backend/application/cash_register/permissions.py:34-53`; `SHIFT_CLOSE`, `Z_CUT_REVIEW` nunca verificados | `tests/architecture/test_cash_register_permissions_catalog.py` | ARQ-SHIFT-003 |
| 8.4 | Responsable original, trazabilidad, esperado vs contado | parcial | Z con esperado/contado (175:88-112); `cash_shift_assignments` nunca escrito | `tests/integration/cash_register/test_z_cut_finalization_flow.py:111-131`; `test_blind_cash_count_flow.py` | ARQ-SHIFT-003 |
| 8.5 | Transiciones validadas en dominio/aplicación | implementado y probado | `backend/domain/cash_register/policies/workflow_policies.py:36-81`; `shift_use_cases.py:128` | `tests/unit/cash_register/test_cash_register_domain.py:46-100` | — |
| 8.6 | Impedir dos turnos incompatibles por caja/cajón | parcial (sólo base local) | Índices únicos parciales (175); central sin unicidad (`migrations/pg/p004_central_cash_finance_credit_loyalty.py:28-40`) | `test_cash_shift_lifecycle.py:72` (sólo cajero) | ARQ-SHIFT-004, ARQ-SYNC-001, ARQ-HYB-001 |
| 8.7 | Integración por contratos/eventos, sin escrituras cruzadas | parcial | Cliente anticorrupción síncrono `backend/infrastructure/integrations/sales_cash_effects_client.py`; outbox a Finanzas | `tests/architecture/test_cash_sales_boundary.py`, `test_cash_finance_treasury_boundary.py` | SDLC-CASH-001/002 (existentes) |
| 8.8 | Concurrencia contra doble cierre, movimientos repetidos | parcial | Doble cierre bloqueado (`repositories.py:94-100`); `set_lifecycle` sin CAS (`repositories.py:58-61`); `BEGIN` diferido (`backend/infrastructure/db/transaction.py:103`) | `test_cash_ledger_flow.py:136`; concurrentes: ninguna | ARQ-SHIFT-004 |

## §9 Operación offline y servicio local

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 9.1 | Terminal offline no finge conocer operaciones de otras | ausente | `backend/domain/offline/policies/offline_read_policy.py` sin consumidor; `offline_status` fijo en ONLINE (`application_context.py:347`) | ninguna | ARQ-HYB-002 |
| 9.2 | Servicio local coordina caja/turno/inventario sin internet | documentado no implementado | Sólo el requisito; SQLite por terminal + candado exclusivo (`frontend/desktop/app.py:113-138`) | ninguna | ARQ-HYB-001 |
| 9.3 | Si cae el servicio local, operaciones de coordinación se bloquean; reconexión | ausente | `backend/application/cash_register/offline_sync.py:154-166` sólo detiene transporte | `tests/integration/cash_register/test_cash_offline_sync.py` (replicación) | ARQ-HYB-002 |

## §10 SQLite, FastAPI, PostgreSQL y sincronización

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 10.1 | PostgreSQL nunca expuesto; FastAPI es la frontera | parcial | uvicorn en 127.0.0.1 tras proxy (`central_app.py:12-14`), sin artefactos | `test_sync_api_end_to_end.py:171` | ARQ-HYB-003 |
| 10.2 | Cola, ids únicos, reintentos, idempotencia servidor, estados, versionado, conflictos | parcial | UUIDv7 `backend/shared/ids.py:47-65`; hash y versión de sobre `backend/shared/sync/replication_envelope.py:136-141`; dedup `central_ingestion.py:163-201`; `sync_conflicts` nunca se resuelve | `tests/unit/central_sync/test_central_ingestion.py`; `test_replication_outbox.py` | SDLC-SYNC-002/004, ARQ-SYNC-002 |
| 10.3 | Reenvío/doble clic/reinicio nunca crea segunda venta | defectuoso | Sync OK; POS genera `operation_id` por clic (`frontend/desktop/modules/sales_pos/sales_pos_presenter.py:128,135,412,417`); `sale_payments` sin `operation_id` | `test_sync_api_end_to_end.py:91`; POS: ninguna | ARQ-IDEM-001, ARQ-IDEM-002 |
| 10.4 | Autoridad por entidad; sin LWW para inventario/caja/turno/contabilidad | defectuoso | Conflictos por estación (`backend/infrastructure/central/sync_inbox_repository.py:240-257`); LWW crédito/lealtad y org units (`projection_repository.py:182-226`) | `test_central_ingestion.py:138,150` (confirman por estación) | ARQ-SYNC-001, SDLC-SYNC-003 |
| 10.5 | Contrato y protocolo versionados; auth servicio a servicio; respaldos | parcial | `/api/v1/sync/events`; `StationScopedAuthorizer.allows → True` (`central_ingestion.py:88-95`); nonce en memoria; sin versión mínima | `test_sync_api_end_to_end.py:122-155` | SDLC-SEC-003, SDLC-SEC-005, ARQ-SYNC-004, ARQ-HYB-003 |
| 10.6 | PostgreSQL con adaptador real, migraciones y pruebas | parcial | Adaptadores en `backend/infrastructure/central/*`; p006 fuera de `PG_MIGRATIONS` pero consultada (`sync_inbox_repository.py:37-38`) | `tests/integration/central_pg/*` (no probado en esta sesión) | SDLC-SYNC-001 |

## §11 Login y autorización offline

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 11.1 | Online contra servicio autorizado; offline sólo con permisos guardados y vigencia | ausente | Login siempre local; central sin usuarios (`device_provisioning.py:18-20`) | ninguna | ARQ-OFF-001 |
| 11.2 | Revocación offline, expiración, cambio de rol, pérdida, alto riesgo | parcial | Revocación local en ~3 s (`backend/application/security/session_grant_refresh.py:28-73`); central nunca llega; tokens móviles 15 min (`backend/api/mobile_session.py:35-70`) | `test_contextual_permissions.py:228,255` | ARQ-OFF-001, ARQ-OFF-002, ARQ-SYNC-003 |
| 11.3 | Explicar bloqueos por política offline; revalidar al reconectar | ausente | Mensaje del router existe pero `offline_status` nunca cambia | `tests/unit/shell/router/test_desktop_router_offline.py` (aislado) | ARQ-HYB-002 |

## §12 Duplicados y concurrencia

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 12.1 | Id estable por operación; idempotencia con unicidad en BD | parcial | Caja e inventario OK (`operation_id` UNIQUE); `sale_payments` sin clave (`sales_schema.py:117-125`); apertura de turno y checkout no hacen replay | `tests/test_sales_operation_id_contract.py`; `test_cash_ledger_flow.py:136` | ARQ-IDEM-001, ARQ-IDEM-002, SDLC-CORE-002 |
| 12.2 | Transiciones concurrentes controladas | parcial | Inventario con versión; ventas sin comparar versión (`sale_repository.py:60-105`); caja sin CAS | `tests/integration/inventory/test_inventory_optimistic_locking.py` | ARQ-IDEM-004, ARQ-SHIFT-004 |
| 12.3 | Estados borrador/pendiente/confirmada/rechazada/compensada | parcial | Vocabulario distinto por entidad (175:66, `sales_schema.py:65`, 350) | ninguna | ARQ-IDEM-005 |
| 12.4 | No borrar trazabilidad; compensar | defectuoso | DELETE+INSERT de hijos de venta (`sale_repository.py:108-174`); `payment_records` nunca REVERSED | `test_cash_ledger_flow.py:147` | ARQ-IDEM-003 |

## §13 Instalación y actualización seguras

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 13.1 | Instalador conserva datos, configuración y rutas | parcial | `uninsneveruninstall` en datos (`installer/windows/spj_setup.iss:21-23,119`); desinstalar borra `install_config.json` (`:151-152`) | `../.github/workflows/windows-release.yml:216-316` (marcador de una fila) | ARQ-INST-002, SDLC-INST-003 |
| 13.2 | Registro seguro de terminal y perfil | documentado no implementado | Perfil en `install_config.json`; sin registro de terminal; 354/p006 sin registrar | ninguna | ARQ-TERM-005 |
| 13.3 | Sin secretos incrustados ni en claro | parcial | Sin secretos en código; `master.key` en claro sin pywin32 (`backend/security/secrets/encrypted_local_secret_store.py:155-182`) | `test_windows_credential_manager_secret_store.py` | ARQ-INST-003 |
| 13.4 | Firma, integridad, compatibilidad, respaldo, migración, validación, recuperación | parcial (flujo del actualizador implementado y probado) | `backend/application/software_updates/update_transaction.py:98-257`; llavero vacío; `update_job.json` escribible; sin `expected_subject` (`backend/infrastructure/updater/updater_main.py:98`); Setup manual migra sin respaldo | `tests/integration/software_distribution/test_update_transaction.py` (10), `test_manifest_and_download.py` (14) | SDLC-INST-001 (ampliado), SDLC-INST-002, ARQ-INST-001 |
| 13.5 | No borrar cola, identidad, sucursal, permisos | parcial, no probado | Migraciones no lo borran; identidad = hostname | ninguna lo afirma | ARQ-INST-002, ARQ-TERM-001 |
| 13.6 | Compatibilidad offline, versiones mínimas, rollout, sin destructivas sin respaldo | parcial | Rollout por porcentaje/sucursal (`backend/domain/software_distribution/eligibility.py:144-150`); central sin versión mínima | `tests/unit/software_distribution/test_domain_policies.py` (23) | ARQ-SYNC-004, ARQ-INST-001 |

## §14 Seguridad y auditoría

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| 14.1 | Registrar autenticaciones, permisos, terminales, caja, sync, conflictos, actualizaciones, admin | defectuoso | `audit_sink` no-op en login (`authenticate_user_use_case.py:71`); auditoría en ~15 tablas; cambios de permisos sí auditados (`save_user_permissions_use_case.py:113`) | `tests/integration/shared/test_audit_trail.py`; seguridad: ninguna | ARQ-AUD-001, ARQ-AUD-002 |
| 14.2 | Terminal no altera su sucursal ni privilegios | defectuoso | Central rechaza sucursal ajena (`central_ingestion.py:147-153`); local re-ancla sin control | ninguna | ARQ-TERM-002 |
| 14.3 | Límites de reintentos, secretos, red local | parcial | Bloqueo 5/900 s por usuario (`backend/security/sessions/account_lockout_policy.py:21`); API local en 127.0.0.1 (`backend/api/service_host.py:15,81`) | `tests/integration/security/test_authenticate_user_use_case.py` | ARQ-AUD-003, SDLC-SEC-005 |

## §15 Pruebas de aceptación

| # | Escenario | Estado | Prueba que lo cubre | Ítem que debe aportarla |
|---|---|---|---|---|
| T1 | Usuario de A en POS de B → denegado | implementado y probado | `tests/integration/security/test_contextual_permissions.py::test_a_user_without_a_role_at_the_station_site_cannot_open_a_session` | — |
| T2 | Usuario de A y B → limitado al ámbito activo | implementado y probado | `test_contextual_permissions.py::test_the_session_operates_the_station_site_not_the_users_home` | — |
| T3 | Logística transversal sin sucursal artificial | parcial | `tests/integration/transfers/test_transfer_full_cycle_32cfbf.py` (sin autorización) | ARQ-SCOPE-001 |
| T4 | Módulo no autorizado inaccesible en UI y API | parcial | `test_profiles_and_schema_gate.py::test_not_installed_module_is_denied_even_to_the_administrator` (UI); API: ninguna | ARQ-TERM-006 |
| T5 | Dos usuarios secuenciales sin herencia | parcial | sólo mocks | ARQ-SESS-001 |
| T6 | Cajero abre en A; gerente consulta en B | ausente | ninguna | ARQ-SHIFT-002, ARQ-HYB-001 |
| T7 | Dos terminales con servicio local sin turnos duplicados | ausente | ninguna | ARQ-HYB-001 |
| T8 | Doble clic/reintento/timeout/reinicio → una operación | parcial | `test_sync_api_end_to_end.py::test_a_lost_response_after_the_server_commit_is_settled_as_duplicate`; POS: ninguna | ARQ-IDEM-001, ARQ-IDEM-002 |
| T9 | Dos usuarios confirman/cierran a la vez | parcial | `tests/integration/inventory/test_inventory_optimistic_locking.py`; caja: ninguna | ARQ-SHIFT-004, ARQ-IDEM-004 |
| T10 | Cae internet / servicio local / reinicio → cola persiste | parcial | `test_replication_outbox.py::test_transport_down_keeps_everything_queued_with_jittered_backoff` | ARQ-HYB-002 |
| T11 | Permiso revocado offline → política de vigencia | ausente | ninguna | ARQ-OFF-001 |
| T12 | Actualización OK/fallida/rollback preserva datos y pendientes | parcial | `test_update_transaction.py::test_failed_migration_restores_the_database_and_previous_version` (no verifica cola/identidad) | ARQ-INST-002 |
| T13 | Migración SQLite y PostgreSQL con respaldos | parcial | `tests/integration/software_distribution/test_backup_relocation_lock.py`; PG sin respaldo | ARQ-INST-001, ARQ-HYB-003 |
| T14 | Auditoría de acciones, alcance, actor real | parcial | `test_audit_trail.py::test_the_branch_is_recorded_when_there_is_one`; actor por defecto 'Sistema' | ARQ-AUD-002 |

## Ampliaciones de ítems existentes (no se crearon ítems nuevos)

- **SDLC-SYNC-003:** la proyección de unidades organizacionales también es última-escritura-gana por el reloj de la estación (`backend/infrastructure/central/projection_repository.py:217-226`).
- **SDLC-INST-001:** `AuthenticodeVerifier` no recibe `expected_subject` (`backend/infrastructure/updater/updater_main.py:98`; `installer_trust.py:50`), así que acepta cualquier editor con firma válida.
- **SDLC-SEC-004:** la lista de nombres `es_gerente` (`backend/bootstrap/legacy_session_adapter.py:158-162`) y las tablas legacy `login_attempts`, `login_blocks`, `usuarios.intentos_fallidos` (`m000_base_schema.py:183-241`) caen dentro de su alcance.
- **SDLC-SEC-005:** `NonceCache` en memoria por proceso ya está cubierto ("nonce por proceso").

## Hallazgos del barrido que no se convirtieron en ítems

- Un subagente reportó como huérfanas las migraciones 066, 076 y 172; **no es cierto**: están en `migrations/engine.py:77,87,179`. Las huérfanas reales siguen en SDLC-CORE-004.
- `CLAUDE.md` regla 9 (preservar shims de WhatsApp que ya no existen) ya está registrada en `PLAN-MAESTRO.md`.
- §1, §16 y §17 (auditoría, plan de entrega, documentación final) no son requisitos verificables en código; los diagramas y políticas de §17 saldrán como artefactos de Design de cada ítem.
