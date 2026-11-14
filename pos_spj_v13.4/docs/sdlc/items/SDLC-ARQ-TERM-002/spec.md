# SDLC-ARQ-TERM-002 — Especificación

- **Intent:** `items/SDLC-ARQ-TERM-002/intent.md` (aprobado el 2026-10-29, Alfred)
- **Nivel:** T0 (toca `security`, `cash_register`/`sync` de lectura, `migrations/`)
- **Estado:** aprobado por autopiloto (2026-11-02) — pendiente de revisión humana en el PR

Rutas relativas a `pos_spj_v13.4/`. Rama base `claude/erp-financial-bounded-context-uqxz6b` @ `1c4786a7`.

## Situación actual (verificada)

| # | Hecho | Evidencia |
|---|---|---|
| E1 | El caso de uso sólo valida el comando y delega: sin permiso, sin auditoría, sin guardas. | `backend/application/use_cases/set_installation_branch_use_case.py:22-28` |
| E2 | El único control de permiso está en el presentador, y es el genérico `CONFIGURACION.empresa.editar`. | `frontend/desktop/modules/configuracion/configuracion_presenter.py:1179-1198` (línea 1185) |
| E3 | El caso de uso se cablea sin política ni auditoría. | `frontend/desktop/modules/configuracion/configuracion_routes.py:203-204,292` |
| E4 | El repositorio hace un `UPSERT` en `configuraciones` sin transacción propia (los repositorios no confirman). | `backend/infrastructure/db/repositories/settings/installation_branch_repository.py:48-69`; `.../settings/base.py:1-3` |
| E5 | `CompanyProfileService.set_installation_branch` es una segunda puerta sin autorización, hoy sólo usada por el caso de uso y por pruebas. | `backend/application/configuracion/settings_services.py:176-186`; `grep` de `set_installation_branch(` en `backend/ frontend/` |
| E6 | Sin ancla, la sesión toma en silencio la sucursal propia del usuario. | `backend/bootstrap/application_context_builder.py:123-129` |
| E7 | El aprovisionamiento escribe el ancla; el esquema base también la siembra. | `backend/security/provisioning/provision_installation_use_case.py:189-193`; `migrations/m000_base_schema.py:3156-3161` |
| E8 | El coordinador de login ya maneja `SiteAccessDeniedError`: revoca la sesión recién abierta y vuelve al login con el motivo. | `frontend/desktop/auth/authentication_coordinator.py:87-98` |
| E9 | Ya existe el mecanismo que oculta y rechaza módulos operativos por capacidad del sitio (menú, router y evaluador de permisos, administrador incluido). | `backend/domain/organization/site_capabilities.py:23-55`; `backend/bootstrap/permission_evaluator.py:28-33`; `frontend/desktop/shell/router/desktop_router.py:150` |
| E10 | Registro central de equipos: la tabla local `device_enrollment` está en `migrations/standalone/354_device_enrollment.py`, pero **no** está registrada en el motor (la lista termina en 353, `migrations/engine.py:359-360`) ni la lee nadie (`grep device_enrollment` en `backend frontend tests` sin resultados). En el central, la reasignación ya existe y se audita (`backend/application/sync/device_provisioning.py:376-396`). |
| E11 | Turnos de caja: estados terminales `CLOSED`, `FORCE_CLOSED`, `CANCELLED`. | `migrations/standalone/175_cash_register_bounded_context_schema.py:30` |
| E12 | Sincronización: estados de sobre PENDING → IN_FLIGHT → SYNCED/RETRY/CONFLICT/DEAD; DEAD es rechazo permanente; los hechos sin sobre aún se preparan desde los outbox de contexto (`DEFAULT_SOURCES`). | `backend/application/sync/replication_outbox.py:6-18`; `backend/infrastructure/sync/replication_sources.py:47-56,131-159` |
| E13 | Rastro de auditoría vigente en la rama base: `audit_logs` vía `SqliteAuditLogRepository.record(action, entity, entity_id, actor, operation_id, details, before, after, branch_id)`. | `backend/infrastructure/db/repositories/settings/audit_log_repository.py:44-84` |
| E14 | Estándar de permisos: códigos `MODULO.accion` en `ConfiguracionPermissions`; el catálogo los deriva solo; `require()` falla cerrado; la sembradura por función sigue el patrón de la 339. | `backend/application/configuracion/permissions.py:18-110`; `backend/application/security/permission_catalog.py:58-82`; `backend/application/configuracion/authorization.py:100-116`; `migrations/standalone/339_seed_software_update_permissions.py` |
| E15 | Acceso total = `system_owner` + `admin/superadmin/administrador`. | `backend/security/permissions/principals.py:23-30` |

## Comportamiento esperado

**R1 · Permiso específico verificado en backend.** `SetInstallationBranchUseCase` exige `CONFIGURACION.estacion.reanclar` con `ConfiguracionAuthorizationPolicy.require()` sobre el actor del comando. Sin política cableada falla cerrado (`unwired`). El presentador deja de decidir el permiso (sólo traduce el error); `CONFIGURACION.empresa.editar` ya no basta.

**R2 · Aprobación central (decisión 2026-11-02).** Si la estación está vinculada al registro central (fila `device_enrollment` con `status='ENROLLED'`), el re-anclaje local se rechaza con `CENTRAL_APPROVAL_REQUIRED` y el motivo «se reasigna desde el registro central». Si no hay registro central (tabla ausente o sin vinculación vigente — el caso de todas las bases hoy, E10), basta el permiso local.

**R3 · Turno abierto.** Se rechaza (`OPEN_CASH_SHIFT`) si la base local tiene algún turno de caja en estado no terminal (E11) en una sucursal distinta de la de destino. Cubre la sucursal anclada actual y el caso de reparación sin ancla.

**R4 · Pendientes de sincronizar.** Si la estación participa en replicación (≥ 1 fila en `replication_stations`), se rechaza (`PENDING_SYNC`) mientras haya sobres en `PENDING`, `IN_FLIGHT`, `RETRY` o `CONFLICT`, o hechos de los outbox de `DEFAULT_SOURCES` que aún no tienen sobre. `SYNCED` y `DEAD` (terminal, E12) no cuentan. Sin replicación registrada no hay canal de sincronización y no hay pendientes (coherente con la decisión «sin registro central, sólo permiso local»).

**R5 · Candado y atomicidad.** El cambio corre en una unidad de trabajo (`TransactionalUnitOfWork`): primero escribe el ancla (toma el candado de escritura de SQLite), luego evalúa R2–R4 sobre ese estado y, si alguna falla, revierte. Ancla y auditoría se confirman juntas o no se confirma nada.

**R6 · Auditoría.** Cada intento que llega al caso de uso deja una fila en `audit_logs`, `modulo='CONFIGURACION'`, `accion='instalacion.reanclar'`, `entidad='instalacion'`, `entidad_id`=sucursal destino, `usuario`=actor, `sucursal_id`=destino, `valor_antes`=`{"branch_id","branch_name"}` (o `{}` sin ancla), `valor_despues`=destino, `detalles` con `terminal=<workstation_id>`, `resultado=APLICADO|RECHAZADO`, `motivo=<código>` y `operation_id`. Los rechazos (permiso, R2, R3, R4) se registran en una transacción aparte, tras revertir. Nunca se registran secretos.

**R7 · Idempotencia.** Re-anclar a la sucursal ya anclada no escribe ni audita y devuelve éxito con `changed=False` (doble clic, reintento). Destino inexistente o inactivo: `ValueError` como hoy (sin auditoría, es validación de captura).

**R8 · Sin fallback silencioso.** Sin ancla válida, `ApplicationContextBuilder` ya no usa la sucursal propia del usuario:
- si el usuario tiene `CONFIGURACION.estacion.reanclar` (evaluado como en la sesión, acceso total incluido), se abre una **sesión de reparación**: `branch_id=''` y `site_capabilities=frozenset()` — el mecanismo E9 oculta y rechaza Ventas, Caja, Inventario, Transferencias, Mermas, Compras, Producción, Logística, Pedidos, Finanzas, CRM y BI; Configuración queda disponible para anclar;
- si no, se rechaza con `StationNotAnchoredError` (subclase de `SiteAccessDeniedError`), que el coordinador ya convierte en revocación de sesión + motivo (E8).
El flujo de provisión no cambia: escribe el ancla (E7).

**Bordes.** Offline: todo es local, no hay red en el camino. Concurrencia: R5. Multi-sucursal: R3 mira cualquier sucursal ≠ destino. Permisos: R1/R8. Varias terminales: cada una tiene su SQLite; la coordinación entre terminales es SDLC-ARQ-HYB-001.

## Diseño

- **Capas:** `application/` (caso de uso, comando), `domain/settings/exceptions.py` (error), `infrastructure/db/repositories/settings/` (consultas de guarda + UoW), `bootstrap/` (constructor de contexto), `frontend/…/configuracion/` (cableado y traducción de errores), `migrations/` (sembrado).
- **Reutiliza:** `SqliteInstallationBranchRepository` (se le agregan las consultas de guarda: es el dueño de "¿qué sucursal es ésta?"), `SqliteAuditLogRepository`, `ConfiguracionAuthorizationPolicy`/`SessionPermissionChecker`, `TransactionalUnitOfWork`, `DEFAULT_SOURCES`, `PermissionEvaluator`, `site_capabilities`, `SiteAccessDeniedError`. No se crea tabla, servicio ni evento nuevo.
- **No se reutiliza** `SqliteOrgUnitRepository.open_cash_shifts` (`org_unit_repository.py:143-149`): no excluye `CANCELLED` y bloquearía para siempre por un turno cancelado; además mira sólo un sitio.
- **Contratos:**
  - `SetInstallationBranchCommand(operation_id, branch_id, user_name, workstation_id="")`.
  - `SetInstallationBranchUseCase(uow_factory, authorization=None)`; `execute(cmd) -> UseCaseResult(entity_id=destino, data={"branch_name", "previous_branch_id", "changed"})`.
  - Errores: `ConfigurationPermissionDeniedError` (R1), `InstallationBranchChangeRejectedError(code, message)` con `code ∈ {CENTRAL_APPROVAL_REQUIRED, OPEN_CASH_SHIFT, PENDING_SYNC}`, `ValueError` (destino inválido).
  - `InstallationBranchUnitOfWork(connection)` con `.installation_branch` y `.audit_log`.
  - Repositorio: `central_enrollment_active() -> bool`, `open_cash_shifts_outside(branch_id) -> int`, `pending_sync_count() -> int`.
  - `StationNotAnchoredError(SiteAccessDeniedError)`.
- **Se elimina** `CompanyProfileService.set_installation_branch` (E5): dejaría una ruta sin autorización ni auditoría. La lectura `get_installation_branch` se conserva.

## Datos y migraciones

- **357 `357_seed_installation_reanchor_permission.py`:** siembra `CONFIGURACION.estacion.reanclar` en `rol_permisos` para `system_owner` y `admin` (patrón 339; idempotente; no borra ni cambia otras filas, §3). Ningún otro rol lo recibe de fábrica (mínimo privilegio; se otorga desde la matriz). Sin cambios de esquema.
- **Reversa:** `DELETE FROM rol_permisos WHERE upper(modulo)='CONFIGURACION' AND accion='estacion.reanclar'` y borrar la versión `357` de `schema_migrations`.
- **Prueba sobre copia:** sólo bases creadas en un directorio temporal (`make_db()` + motor); dos corridas seguidas = mismo número de filas.

## Seguridad y auditoría

Permiso `CONFIGURACION.estacion.reanclar` (módulo CONFIGURACION, acción `estacion.reanclar`, ámbito empresa — Configuración no exige sucursal activa, `authorization.py:64-65`). Validado en el caso de uso; sesión de reparación validada en el constructor. Auditoría R6.

## Criterios de aceptación

1. Sin `CONFIGURACION.estacion.reanclar` el caso de uso rechaza, aunque tenga `CONFIGURACION.empresa.editar`; el ancla no cambia y queda una fila `RECHAZADO motivo=PERMISSION_DENIED`.
2. Sin política cableada el caso de uso falla cerrado.
3. Con turno abierto en la sucursal anclada: rechazo `OPEN_CASH_SHIFT`, ancla intacta, fila de rechazo. Un turno `CLOSED`/`CANCELLED` no bloquea.
4. Con replicación registrada y un sobre `RETRY`/`CONFLICT`, o un hecho sin sobre: rechazo `PENDING_SYNC`; con sólo `SYNCED`/`DEAD`: procede.
5. Con `device_enrollment` `ENROLLED`: rechazo `CENTRAL_APPROVAL_REQUIRED`; sin esa tabla: procede con permiso local.
6. Éxito: ancla nueva + una fila `audit_logs` con actor, terminal, antes/después, `operation_id`, `resultado=APLICADO`, en la misma transacción.
7. Repetir el mismo re-anclaje no escribe ni audita (`changed=False`).
8. Sin ancla, un usuario sin el permiso no obtiene contexto (`StationNotAnchoredError`); con el permiso obtiene sesión de reparación sin sucursal ni módulos operativos; ya no se usa la sucursal propia.
9. Migración 357 siembra el permiso a `system_owner` y `admin`, es idempotente y está en el motor.
10. Se conservan: anclaje correcto desde Configuración, rechazo de sucursal inexistente/inactiva, `get()` devuelve `None` si la sucursal desapareció, el login usa el ancla cuando existe.

## Riesgos y alternativas descartadas

- **Estación registrada para replicación sin servidor central** (p. ej. abrió la vista de sincronización de Caja, que la registra — `backend/infrastructure/desktop/cash_register_factory.py:174-176`): sus hechos nunca se sincronizan y R4 la bloquea mientras no haya central. Es el comportamiento seguro que pide el intent; se informa en el PR para que el responsable decida si abrir un ítem.
- Descartado: cerrar el login a todos sin ancla (dejaría la estación inutilizable sin forma de repararla); usar `CONFIGURACION.empresa.editar` (el intent pide un permiso específico); llamar al central para aprobar (no hay transporte ni vinculación en runtime, E10; es TERM-004/SYNC).
- Fuera de alcance (intent): propagar el cambio a la sesión viva (SDLC-SET-001), protección criptográfica del ancla (TERM-005), fuente canónica de terminal (TERM-001); `workstation_id` sigue siendo el que da la sesión.

## Decisiones que requieren aprobación

Ninguna abierta. Fuentes: aprobación central → decisión 2026-11-02 de BACKLOG (TERM-002); «Cambiar sucursal» no re-ancla → decisión SDLC-UI-016 (no se toca); mínimo privilegio y no conceder sin aprobación → `requisitos-arquitectura.md` §3; terminal no altera su sucursal y registro con quién/qué/terminal/id de operación/resultado → §5, §6, §14.
