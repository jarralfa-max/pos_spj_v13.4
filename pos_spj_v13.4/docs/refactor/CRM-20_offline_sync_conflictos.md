# CRM-20 — Offline-first: conflictos de sincronización (§91-92)

Fecha: 2026-08-14. El usuario nombró explícitamente CRM-20 — una fase que
había sido saltada al inicio del pipeline sin que su alcance quedara
documentado en ningún artefacto (verificado: ni
`docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md` ni `docs/refactor/`
tenían registro de qué cubría). Se confirmó el alcance con el usuario antes
de construir nada: offline-first + conflictos de sincronización (§91-92),
la interpretación más probable dado el orden de secciones del master
prompt entre CRM-18 (formularios) y CRM-21 (migración de consumidores).

## Investigación previa (por qué no se extendió `sync/`)

Antes de diseñar nada se investigó la infraestructura de sync YA existente
en el repo. Hallazgo central: `sync/` (mencionado en el CLAUDE.md del
proyecto) es un motor completo — `SyncEngine`, `SyncWorker`,
`ConflictResolver` — pero **hardcodeado a una lista fija de tablas legacy**
(`productos, clientes, ventas, ...`, ninguna de Clientes/CRM) y **nunca se
arranca en producción**: `main.py` no lo importa en ningún lado. Extenderlo
habría significado construir sobre infraestructura muerta, no real.

El patrón real y funcionando más cercano son las columnas `sync_status`
+ dispatcher con backoff/dead-letter que **Inventario/Compras/Transferencias/
Caja/Mermas** ya construyeron cada uno para sí mismos —
`InventoryOutboxDispatcher` (`backend/application/inventory/sync/
outbox_dispatcher.py`) es el único ejemplo genuinamente wireado end-to-end.
Ni `customers`/`crm` ni sus 3 paquetes hermanos tenían ninguna pieza de esto
antes de esta fase — sus tablas `outbox` existen desde CRM-3/CRM-4 pero
nunca las lee ningún dispatcher, mismo tipo de brecha que CRM-26 ya
encontró para el EventBus.

## Alcance elegido (y por qué se recortó del original)

El diseño original consideraba replicar el dispatcher completo de
Inventario (con `sync_dispatch`/`sync_cursor`, retry/backoff, columna
`sync_status` en `customers`/`leads`/`opportunities`). Se recortó
deliberadamente porque:

1. **No existe ningún transporte real a donde despachar** — este repo
   confirmadamente corre hoy sobre un único archivo SQLite compartido
   (`data/spj_pos_database.db`, mismo hallazgo de CRM-25 para WhatsApp), sin
   servidor central ni terminales múltiples reales. Construir un dispatcher
   sin nada al otro lado habría sido fabricar infraestructura decorativa —
   exactamente lo que CRM-26 ya se negó a hacer con el scheduler de
   triggers derivados.
2. **`Customer` ya tiene `version` (CRM-3)** — optimistic concurrency real
   sin agregar ninguna columna nueva. `Lead`/`Opportunity` ya bumpean
   `updated_at` en cada mutación (`_touch()`). Usar lo que ya existe es más
   honesto que inventar un `sync_status` de 5 estados
   (`LOCAL_PENDING/SYNCING/SYNCED/CONFLICT/FAILED`) que ningún productor
   real llenaría todavía — confirmado por la investigación: `LOCAL_PENDING`
   no existe como string en absolutamente ningún lugar del repo hoy.

Lo que sí es real, valioso, y verificable — la garantía concreta de §92
("no sobrescribir silenciosamente") — es lo que se construyó completo:

## Qué se construyó

- **Dominio**: `CustomerSyncConflict` (`backend/domain/customers/`) con los
  6 tipos que §92 agrupa ahí (`CUSTOMER_UPDATED_REMOTELY`,
  `DUPLICATE_CREATED`, `CONTACT_CONFLICT`, `ADDRESS_CONFLICT`,
  `CONSENT_CONFLICT`, `CREDIT_CONFLICT`); `CRMSyncConflict`
  (`backend/domain/crm/`) con los 4 restantes (`LEAD_ASSIGNMENT_CONFLICT`,
  `OPPORTUNITY_STAGE_CONFLICT`, `TASK_STATUS_CONFLICT`,
  `CASE_ASSIGNMENT_CONFLICT`) — exactamente **dos** entidades, como nombra
  §92 literalmente (no una por sub-paquete). `SyncConflictStatus`
  (OPEN→RESOLVED_LOCAL/RESOLVED_REMOTE/RESOLVED_MERGED) duplicado en ambos
  paquetes, mismo criterio de no cruzar vocabulario de dominio entre
  `customers`/`crm` que ya se sigue en el resto del pipeline.
- **Detección** (`DetectCustomerSyncConflictUseCase`/
  `DetectCRMSyncConflictUseCase`): system-triggered, sin `actor_user_id`
  (mismo razonamiento que CRM-13/CRM-26 ya establecieron para casos de uso
  reactivos). Compara la versión/timestamp que la mutación entrante
  *pensaba* estar editando contra la real actual; si difieren, crea el
  registro de conflicto y **nunca aplica el cambio entrante** — verificado
  con test: el dato local sobrevive intacto tras un conflicto detectado.
  El diseño de `DetectCRMSyncConflictUseCase` es agnóstico de tipo de
  entidad a propósito (recibe `local_updated_at` ya obtenido por quien
  llama, no lo busca él mismo) — evita que este archivo tenga que importar
  las 4 UnitOfWork distintas que Lead/Opportunity/Task/Case usan (Case vive
  en `customer_service`, un bounded context hermano).
- **Resolución** (`ResolveCustomerSyncConflictUseCase`/
  `ResolveCRMSyncConflictUseCase`): permission-gated
  (`SYNC_CONFLICTS_RESOLVE`), exige una decisión explícita LOCAL/REMOTE/
  MERGED, nunca automática. Para Customer, aplica los mismos campos
  editables que `UpdateCustomerUseCase` ya expone
  (`display_name`/`legal_name`/`commercial_name`) — mismo allowlist, no un
  camino de escritura más amplio. Para CRM, la aplicación real de campos
  REMOTE/MERGED solo está conectada para **LEAD** (el caso probado
  end-to-end); OPPORTUNITY/TASK/CASE pueden detectarse y resolverse a
  RESOLVED_LOCAL/RESOLVED_REMOTE/RESOLVED_MERGED (el conflicto se cierra),
  pero la aplicación de datos remotos/fusionados para esos tres queda
  como brecha documentada, no un no-op silencioso — el resultado de
  `ResolveCRMSyncConflictUseCase` incluye `applied: bool` para que el
  llamador sepa si el dato realmente cambió.
- **Permisos**: `SYNC_CONFLICTS_VIEW`/`SYNC_CONFLICTS_RESOLVE` en ambos
  catálogos (`CustomerPermissions`/`CRMPermissions`), reflejados en
  `core/security/permission_catalog.py`.
- **Esquema**: `customer_sync_conflicts`/`crm_sync_conflicts`, migración
  195 (solo invoca las funciones de esquema existentes, aditiva).

## Explícitamente fuera de alcance

- Dispatcher de outbox con retry/backoff (`sync_dispatch`/`sync_cursor`,
  patrón de Inventario) — no hay transporte real a donde despachar hoy.
- Columna `sync_status` en `customers`/`leads`/`opportunities` — la
  detección de conflictos ya funciona sin ella (version/`updated_at`
  existentes); agregarla sin un productor real de `LOCAL_PENDING`/`SYNCING`
  habría sido vocabulario decorativo.
- Aplicación de campos REMOTE/MERGED para OPPORTUNITY/TASK/CASE.
- UI de resolución de conflictos en `customers_crm` — el backend está
  completo y probado, falta pantalla.
- `DUPLICATE_CREATED`/`CONTACT_CONFLICT`/`ADDRESS_CONFLICT`/
  `CONSENT_CONFLICT`/`CREDIT_CONFLICT` — los 5 tipos restantes de
  `CustomerSyncConflictType` existen en el enum y el CHECK del esquema,
  pero ningún flujo real los dispara todavía (solo
  `CUSTOMER_UPDATED_REMOTELY` se ejercita end-to-end en los tests) — el
  mecanismo de detección los soporta a todos por igual, falta el
  productor de cada uno.

## Verificación

```bash
python -m pytest tests/unit/customers/test_customer_sync_conflict_entity.py \
  tests/unit/crm/test_crm_sync_conflict_entity.py \
  tests/integration/customers/test_customer_sync_conflict_application.py \
  tests/integration/crm/test_crm_sync_conflict_application.py -v
```
18 tests nuevos, todos pasando (7 unitarios de entidad + 11 de integración
detección/resolución/permisos).

```bash
python -m pytest tests/unit/crm/ tests/integration/crm/ tests/unit/customers/ \
  tests/integration/customers/ tests/unit/customer_service/ \
  tests/integration/customer_service/ tests/architecture/test_customers_crm_*.py -q
```
708 tests pasando, cero regresiones.

Suite completa `tests/architecture/` corrida en segundo plano para el
chequeo final repo-wide, mismo protocolo que CRM-25/26.

## Pendiente (fases futuras)

- Dispatcher real, cuando exista un transporte (servidor central o
  replicación entre terminales) a donde despachar.
- Aplicación REMOTE/MERGED para OPPORTUNITY/TASK/CASE.
- Productores reales para los 5 tipos de conflicto de Customer sin
  ejercitar todavía.
- Pantalla de resolución de conflictos en `customers_crm`.
