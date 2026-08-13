# CRM-11 — Calidad, Duplicados, Fusión, Importación

Fecha: 2026-08-13. Depende de CRM-0 (auditoría), CRM-1 (guardrails), CRM-2
(seguridad — `CustomerPermissions.DUPLICATES_*`/`DATA_QUALITY_*`/`IMPORT*`
ya existían sin consumidor, así como `CustomerSegregationOfDutiesPolicy.
enforce_merge_proposer_not_self_approving()`/`enforce_sensitive_import_
approver_distinct()`, ambas sin llamador desde CRM-2), CRM-3 (Customer
Master — `Customer.mark_merged()` fue construida ahí explícitamente "Set
by the CRM-11 merge use case"; `CustomerDuplicatePolicy` fue construida ahí
con la nota explícita "CustomerDuplicateCandidate persistence and the
merge workflow itself are CRM-11").
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §45-47,
§73-74. §48 (exportación) queda fuera de alcance — el usuario invocó esta
fase nombrando "importación", no "exportación"; `EXPORT`/`BULK_UPDATE`
siguen sin consumidor.

## Decisión de ubicación: extiende `customers`, no un paquete nuevo

Como CRM-10 con `crm`, esta fase extiende `backend/domain/customers/`,
`backend/application/customers/` y `customers_crm_schema.py` — el mismo
paquete que CRM-3 construyó. Confirmado por dos señales inequívocas del
propio código: los permisos `DUPLICATES_*`/`DATA_QUALITY_*`/`IMPORT*` ya
viven en `CustomerPermissions` (no en `CRMPermissions`), y
`CustomerDuplicatePolicy`/`Customer.mark_merged()` fueron construidas en
`customers` con comentarios explícitos apuntando a esta fase.

## Decisiones de alcance (documentadas, no adivinadas)

- **Ningún permiso nuevo fue necesario.** Primera fase de todo el
  pipeline CRM-0..11 sin adición retroactiva — CRM-2 ya había catalogado
  `DATA_QUALITY_VIEW/RESOLVE`, `DUPLICATES_VIEW/REVIEW/DISMISS/MERGE`,
  `IMPORT`/`IMPORT_APPROVE` completos. Verificado explícitamente:
  `ALL_CUSTOMER_PERMISSIONS` sigue en 77 (igual que tras CRM-9); el único
  hallazgo del diff contra el catálogo es `CLIENTES.credito` — la entrada
  plana legacy que `permissions.py` ya documenta como preservada a
  propósito para `modulos/clientes.py`, ajena a esta fase.
- **`CustomerDuplicateCandidate` (§45): estados literales del prompt** —
  DETECTED→UNDER_REVIEW→{CONFIRMED_DUPLICATE,DISMISSED}; CONFIRMED_
  DUPLICATE→MERGED (puesto por `ExecuteCustomerMergeUseCase`, no por esta
  entidad — mismo reparto de responsabilidad que `Customer.mark_merged()`).
  `DetectDuplicateCandidatesUseCase` reutiliza `CustomerDuplicatePolicy.
  find_matches()` (ya usada por `CreateCustomerUseCase`/`ConvertLeadUseCase`
  para prevenir en creación) en un escaneo por pares sobre toda la base;
  idempotente vía `get_active_pair()` — un par ya cubierto por un
  candidato no terminal no se vuelve a detectar.
- **`CustomerMergeRecord`: solo tres estados** (PROPOSED→EXECUTED/REJECTED),
  sin un APPROVED intermedio persistido. El prompt describe el *flujo* de
  fusión pero no una lista de estados como sí hace para duplicados;
  aprobación y ejecución colapsan en una sola llamada en caliente, mismo
  patrón que `UpdateCustomerCreditLimitUseCase(override=True)` ya usa para
  incrementos extraordinarios de crédito — nada distingue "aprobado" de
  "ejecutado" que amerite su propio estado y caso de uso.
- **`ExecuteCustomerMergeUseCase` consume DOS mecanismos a la vez**:
  `CustomerAuthorizationPolicy.authorize_exception()` (§74 nombra
  explícitamente "fusión de clientes" como autorización en caliente —
  tercer consumidor real, tras CRM-8 crédito y CRM-9 anonimización) Y
  `CustomerSegregationOfDutiesPolicy.enforce_merge_proposer_not_self_
  approving()` (mensaje de dominio específico para fusión, en vez de
  apoyarse solo en el invariante genérico `authorized_by != requested_by`
  del grant). Intencional: consumir el método exacto que CRM-2 construyó
  por nombre para esta acción, no solo su efecto genérico.
- **La resolución de datos de fusión NUNCA toca otros bounded contexts.**
  "Notifica bounded contexts... nunca modifica tablas externas
  directamente" (§45) se cumple literalmente: `ExecuteCustomerMergeUseCase`
  reasigna `customer_contacts`/`customer_addresses`/`customer_accounts` (sin
  restricción de unicidad, reasignación directa) y resuelve
  `customer_tax_profiles` (SÍ tiene `UNIQUE(customer_id)` — si el maestro
  ya tiene perfil fiscal, el del cliente fusionado se descarta; si no, se
  reasigna) — todo dentro de `customers`. Consentimientos (customer_
  privacy), crédito (customer_credit) y propietario/cartera (crm) NO se
  tocan aquí; el evento `CUSTOMER_MERGE_EXECUTED` es la única señal hacia
  esos bounded contexts, y reaccionar a él queda como trabajo futuro
  explícito (mismo límite que CRM-8 sostuvo para CxC y CRM-9 para
  anonimización).
- **`CustomerDataQualityService` evalúa solo 5 de las ~9 reglas de §46** —
  las que solo necesitan datos propios de `customers` (nombre incompleto,
  teléfono/correo/RFC inválido, dirección incompleta), reutilizando los
  value objects `PhoneNumber`/`EmailAddress` ya existentes (su
  `__post_init__` ya valida, no hacía falta reimplementar el regex) más
  una verificación de forma de RFC nueva y deliberadamente ligera (sin
  dígito verificador — un value object RFC completo sería sobre-ingeniería
  para lo que es un heurístico de calidad, no una puerta de validación
  dura). Las cinco reglas restantes (consentimiento faltante, crédito
  inconsistente, lead sin seguimiento, oportunidad sin próxima actividad,
  caso sin propietario) necesitan datos de otros bounded contexts y quedan
  explícitamente diferidas a CRM-12 (Customer 360), el punto natural de
  agregación cross-context. "Duplicado probable" tampoco es una regla
  aquí — ese terreno ya lo cubre el flujo dedicado de
  `CustomerDuplicateCandidate`, no se duplica (nunca mejor dicho) como un
  segundo mecanismo con su propia vía de resolución.
- **Detección y escaneo se gatean con los permisos "ver", no "resolver"/
  "revisar".** Correr un escaneo es una acción de lectura/refresco —nada
  se decide sobre un caso concreto todavía—, mismo razonamiento que
  CRM-10 aplicó a sus query services. Las transiciones por-registro
  (revisar/confirmar/descartar duplicados; reconocer/corregir/descartar
  problemas de calidad) sí usan los permisos de acción específicos.
- **Importación sensible round-tripea las filas como JSON crudo en el
  repositorio, no en la entidad de dominio.** `CustomerImportBatch` (la
  entidad) solo modela conteos y su propio ciclo de vida — las filas de un
  lote sensible deben sobrevivir hasta que un segundo aprobador,
  posiblemente en otra sesión, las procese, así que
  `CustomerImportBatchRepository.save_pending_rows`/`get_pending_rows`
  las guarda en una columna `pending_rows_json` — mismo trato de "blob que
  el dominio no necesita modelar" que ya recibe el payload de outbox.
  Corregido durante esta misma fase (no en una iteración posterior): el
  primer borrador dejaba la entidad sin forma de recuperar las filas al
  aprobar, y se corrigió antes de escribir el repositorio.
- **`ImportCustomersUseCase` soporta crear y actualizar en el mismo lote**
  — una fila con `customer_id` actualiza ese cliente existente
  (display_name/legal_name); una fila sin él sigue el flujo de creación
  con detección de duplicados de `CreateCustomerUseCase` (vía
  `CustomerDuplicatePolicy`, extendida en memoria con cada fila creada
  para detectar duplicados *dentro* del mismo lote, no solo contra la base
  ya existente). Ninguna fila mala aborta el lote completo — cada una cae
  en exactamente un conteo (creados/actualizados/rechazados/duplicados/
  errores), tal como pide §47.

## Dominio (extiende `backend/domain/customers/`)

- **`enums.py`** — `DuplicateCandidateStatus` (5), `CustomerMergeStatus`
  (3), `DataQualityIssueStatus` (4), `DataQualityRuleCode` (5),
  `ImportBatchStatus` (6).
- **`entities/customer_duplicate_candidate.py`**,
  **`entities/customer_merge_record.py`**,
  **`entities/customer_data_quality_issue.py`**,
  **`entities/customer_import_batch.py`**.
- **`exceptions.py`** — 8 excepciones nuevas (NotFound + Invalid por cada
  una de las 4 entidades).
- **`events.py`** — 14 eventos nuevos agregados a `CustomerEvents`.
- **`repository_ports.py`** — 4 puertos nuevos, más `reassign_customer_id`
  agregado a los puertos de accounts/contacts/addresses/tax_profiles
  (soporte de fusión) y `save_pending_rows`/`get_pending_rows`/
  `clear_pending_rows` en el puerto de import batches.

## Infraestructura

- **`backend/infrastructure/db/schema/customers_crm_schema.py`** — 4
  tablas nuevas (`customer_duplicate_candidates`, `customer_merge_records`,
  `customer_data_quality_issues`, `customer_import_batches` — esta última
  con la columna `pending_rows_json`) + sus índices, agregadas al mismo
  archivo de CRM-3.
- **`migrations/standalone/191_customers_data_quality_bounded_context_
  schema.py`** — número verificado contra `engine.py` y el directorio de
  migraciones dos veces (antes de empezar y de nuevo justo antes de crear
  el archivo — 191 libre, 200 ya reclamado por una sesión concurrente).
  Solo `CREATE TABLE IF NOT EXISTS`. Bootstrap completo verificado: 587
  tablas totales, las 4 nuevas presentes.
- **`backend/infrastructure/db/repositories/customers/`** — 4
  repositorios nuevos, cableados en `CustomerUnitOfWork`
  (`duplicate_candidates`, `merge_records`, `data_quality_issues`,
  `import_batches`). `customer_child_repositories.py` gana
  `reassign_customer_id()` en accounts/contacts/addresses y
  `reassign_customer_id()`/`delete_for_customer()` en tax_profiles —
  soporte mínimo, aditivo, para la ejecución de fusión.

## Aplicación (extiende `backend/application/customers/`)

- **`services/customer_data_quality_service.py`** — `CustomerDataQualityService`,
  evaluador puro (sin I/O) de las 5 reglas propias del paquete.
- **`use_cases/duplicate_use_cases.py`** — `DetectDuplicateCandidatesUseCase`,
  `ReviewDuplicateCandidateUseCase`, `ConfirmDuplicateCandidateUseCase`,
  `DismissDuplicateCandidateUseCase`.
- **`use_cases/merge_use_cases.py`** — `ProposeCustomerMergeUseCase`,
  `ExecuteCustomerMergeUseCase`, `RejectCustomerMergeUseCase`.
- **`use_cases/data_quality_use_cases.py`** — `RunCustomerDataQualityScanUseCase`
  (idempotente por regla vía `get_open()`), `AcknowledgeDataQualityIssueUseCase`,
  `CorrectDataQualityIssueUseCase`, `DismissDataQualityIssueUseCase`.
- **`use_cases/import_use_cases.py`** — `ImportCustomersUseCase`,
  `ApproveCustomerImportUseCase`, `RejectCustomerImportUseCase`.
- **`queries/customer_duplicate_query_service.py`**,
  **`queries/customer_data_quality_query_service.py`** — flat
  DUPLICATES_VIEW/DATA_QUALITY_VIEW, mismo criterio sin-sufijo-de-alcance
  que CRM-6's `CRMActivityQueryService`.
- **`queries/customer_import_preview_query.py`** — `CustomerImportPreviewQuery`
  (§47's `CustomerImportPreviewQuery`, nombrada explícitamente): dry-run
  puro, sin escritura, mismo cálculo de duplicados/validación que el caso
  de uso real usará, para que el preview y la ejecución nunca diverjan.

## Verificación

```bash
python -m pytest tests/unit/customers/test_quality_duplicates_merge_import_entities.py \
  tests/integration/customers/test_quality_duplicates_merge_import_application.py \
  tests/architecture/test_customers_crm_*.py -v
# 62 passed (calidad/duplicados/fusión/importación) + 21 passed, 1 skipped (guardrails)
```

- 62 tests nuevos (30 unitarios de dominio — incluye
  `CustomerDataQualityService` puro — y 32 de integración con SQLite real:
  detección idempotente de duplicados, ciclo completo revisar→confirmar,
  fusión con resolución real de contactos/direcciones/perfil fiscal
  incluyendo el caso "ambos tienen perfil fiscal", exigencia de segundo
  autorizador distinto en la ejecución de fusión, escaneo de calidad
  idempotente, e importación sensible con SoD verificado — mismo
  usuario rechazado, usuario distinto aprueba y procesa).
- Los 22 guardrails de CRM-1 se re-ejecutaron completos y siguieron en
  verde sin ajustes.
- 692 tests de `tests/unit/{customers,crm,customer_credit,customer_privacy,
  customer_service}/` + sus contrapartes de integración pasan juntos
  (630 previos + 62 nuevos).
- Paridad de catálogo verificada explícitamente: `ALL_CUSTOMER_PERMISSIONS`
  se mantiene en 77 (sin adiciones) — cero drift, primera fase del
  pipeline sin necesidad de un permiso retroactivo.
- Sintaxis limpia en todo el repositorio (incluyendo lo tocado por esta
  fase); bootstrap completo de migraciones verificado (587 tablas, las 4
  nuevas + la columna `pending_rows_json` presentes).

## Pendiente (próximas fases)

- **CRM-12 (Customer 360):** consumidor natural de las cinco reglas de
  calidad diferidas (consentimiento/crédito/lead/oportunidad/caso), y de
  `CustomerDuplicateQueryService`/`CustomerDataQualityQueryService` para
  las tabs "Duplicados"/"Calidad" del expediente.
- **Exportación (§48):** `EXPORT`/`BULK_UPDATE` siguen sin consumidor —
  el usuario no nombró "exportación" al invocar esta fase; `ExportCustomers
  Query`/`ExportCRMActivitiesQuery`/`ExportOpportunitiesQuery` quedan para
  cuando se invoque explícitamente.
- **Reacción de otros bounded contexts a `CUSTOMER_MERGE_EXECUTED`:** hoy
  solo se emite el evento. Que `crm` reasigne leads/oportunidades del
  cliente fusionado, que `customer_credit` consolide exposición, que
  `customer_privacy` fusione historial de consentimiento — todo eso es
  trabajo futuro explícito, no implementado aquí (mismo límite de
  bounded-context que esta fase sostuvo activamente, no un olvido).
