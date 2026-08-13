# CRM-10 — Propietario, Territorios, Carteras, Segmentación, Etiquetas

Fecha: 2026-08-12. Depende de CRM-0 (auditoría), CRM-1 (guardrails), CRM-2
(seguridad — `CRMPermissions.SEGMENTS_*`/`TAGS_*`/`TERRITORIES_*`/
`PORTFOLIOS_*`/`CUSTOMER_OWNER_*` ya existían sin consumidor, así como
`CustomerSegregationOfDutiesPolicy.enforce_ownership_reassignment_justified()`,
sin llamador desde CRM-2), CRM-3 (Customer Master — `Customer.
account_owner_user_id`/`territory_id` y sus métodos `assign_owner()`/
`assign_territory()` fueron construidos ahí explícitamente para que esta
fase los llamara), CRM-4/5/6 (esta fase extiende el mismo paquete `crm`,
no crea uno sibling — ver más abajo).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §33-36.

## Decisión de ubicación: extiende `crm/`, no un paquete sibling nuevo

A diferencia de CRM-7/8/9 (que crearon `customer_service`/`customer_credit`/
`customer_privacy` como bounded contexts sibling nuevos), CRM-10 extiende
`backend/domain/crm/`, `backend/application/crm/`,
`backend/infrastructure/db/repositories/crm/` y `crm_schema.py` — el mismo
paquete que CRM-4/5/6 construyeron. La razón es CRM-2: todo este dominio
(segmentos/etiquetas/territorios/carteras/propietario) ya estaba
catalogado bajo `CRMPermissions`, no bajo `CustomerPermissions` — CRM-2
decidió esa pertenencia desde el principio, esta fase solo la honra.

## Decisiones de alcance (documentadas, no adivinadas)

- **`CustomerOwnership`/`PortfolioAssignment` son logs append-only**,
  mismo patrón que `CustomerConsent` (CRM-9): reasignar nunca sobreescribe
  una fila, captura una nueva. "La actual" se resuelve con `get_latest()`
  (ordenado `created_at DESC, id DESC` — mismo desempate por UUIDv7 que el
  bug corregido en CRM-9). §33-36 lo pide explícitamente para
  `CustomerOwnership` ("con historial de asignación — no solo
  `vendedor_id` plano"); se aplicó el mismo criterio a `PortfolioAssignment`
  por consistencia, aunque el prompt no lo dice tan literalmente ahí.
- **Solo `OwnershipType.PRIMARY` sincroniza con `Customer.
  account_owner_user_id`.** Ese es el único campo denormalizado que
  `CustomerDataScopeResolver` lee para resolver alcance OWN — los otros
  cuatro tipos (`SECONDARY`, `ACCOUNT_MANAGER`, `CREDIT_MANAGER`,
  `SERVICE_OWNER`) son roles informativos sin columna equivalente en
  `Customer`, así que se quedan solo en `crm`.
- **Territorio se sincroniza con `Customer.territory_id` directamente
  (sin permiso "reasignar" separado).** A diferencia de propietario/
  cartera, §73 no menciona "reasignar territorio" como acción con
  requisito de motivo — solo `TERRITORIES_MANAGE` gatea
  `AssignCustomerTerritoryUseCase`, sin split assign/reassign ni SoD.
- **`source` vive en `CustomerSegmentMembership`, no en `CustomerSegment`.**
  El mismo segmento puede acumular miembros de distintas fuentes a lo
  largo del tiempo (uno agregado a mano, otro sugerido por BI) — la fuente
  es un hecho de la membresía puntual, no una propiedad de la definición
  del segmento. Interpretación explícita: el texto condensado del master
  prompt no dice literalmente en qué entidad vive la lista
  `MANUAL/RULE_BASED/IMPORTED/ANALYTICS_GENERATED`.
- **`CustomerSegment.rule_definition` es inerte.** CRM nunca la parsea ni
  la ejecuta — "BI puede sugerir, CRM administra el uso operativo" (§33-36).
  BI evalúa la regla en su propio motor y reporta membresías de vuelta vía
  `AddCustomerToSegmentUseCase(source=RULE_BASED/ANALYTICS_GENERATED)`.
- **`CustomerTagAssignment` no tiene `source`** (a diferencia de
  `CustomerSegmentMembership`) — las etiquetas siempre se aplican por
  acción de un usuario, nunca derivadas de reglas/analítica; y "no
  sustituyen estatus/segmento/riesgo/consentimiento/territorio" (§33-36),
  es decir, no cargan peso de regla de negocio propio que requiera
  trazabilidad de origen.
- **`PORTFOLIOS_ASSIGN` es la única adición retroactiva de permiso** —
  `CRM.carteras.asignar`. §73 ("reasignar cartera... requiere un motivo")
  implica una acción dedicada, distinta de `PORTFOLIOS_MANAGE` (que
  gobierna el catálogo: crear/editar/desactivar una cartera, no la
  membresía de un cliente en ella). Mismo patrón de brecha que
  `TASKS_RESCHEDULE`/`REMINDERS_CREATE` (CRM-6), `SLA_MANAGE` (CRM-7 —
  consumido, no agregado), `CREDIT_CLOSE` (CRM-8),
  `COMMUNICATION_PREFERENCE_*` (CRM-9). **No se agregó** un
  `PORTFOLIOS_REASSIGN` paralelo a `CUSTOMER_OWNER_REASSIGN`: a diferencia
  de leads/oportunidades/tareas/casos/propietario, el catálogo no tiene
  ninguna señal que distinga explícitamente "reasignar cartera" de
  "asignar cartera" como permisos separados — un solo código cubre ambos,
  y es el motivo obligatorio (SoD) el que realmente gatea la reasignación,
  no un segundo permiso. Verificado 1:1 sin drift:
  `ALL_CRM_PERMISSIONS` == `CANONICAL_MODULE_PERMISSIONS["CRM"]`.
- **Assign vs reassign para `CustomerOwnership`** sigue el mismo patrón
  que `AssignCRMTaskUseCase` (CRM-6)/`AssignOpportunityUseCase` (CRM-5):
  `CUSTOMER_OWNER_ASSIGN` si no existe un `CustomerOwnership` previo para
  ese `(customer_id, ownership_type)`, `CUSTOMER_OWNER_REASSIGN` si ya
  existe — y solo entonces se exige motivo vía
  `CustomerSegregationOfDutiesPolicy.
  enforce_ownership_reassignment_justified()`.

## Dominio (extiende `backend/domain/crm/`)

- **`enums.py`** — `OwnershipType` (5 valores), `SegmentMembershipSource`
  (4 valores).
- **`entities/sales_territory.py`**, **`entities/customer_portfolio.py`**,
  **`entities/customer_segment.py`**, **`entities/customer_tag.py`** —
  catálogos simples, mismo patrón `create()`/`deactivate()` que
  `CRMStageDefinition` (CRM-5).
- **`entities/customer_ownership.py`**, **`entities/portfolio_assignment.py`**
  — append-only, `capture()` únicamente (sin métodos de mutación), mismo
  patrón que `CustomerConsent.capture()` (CRM-9).
- **`entities/customer_segment_membership.py`**,
  **`entities/customer_tag_assignment.py`** — append-only-con-`removed_at`
  nulable: `add()`/`remove()`/`is_active()`.
- **`exceptions.py`** — 14 excepciones nuevas (Not­Found + Invalid por
  cada una de las 8 entidades, salvo las tres append-only puras que no se
  buscan por id propio en ningún caso de uso salvo remoción, que sí tiene
  su propio NotFound: `CustomerSegmentMembershipNotFoundError`,
  `CustomerTagAssignmentNotFoundError`).
- **`events.py`** — 16 eventos nuevos agregados a `CRMEvents` (territorio,
  cartera, propietario, segmento, etiqueta — crear/desactivar/asignar/
  reasignar/agregar-miembro/remover-miembro según aplique).
- **`repository_ports.py`** — 8 puertos nuevos.

## Infraestructura

- **`backend/infrastructure/db/schema/crm_schema.py`** — 8 tablas nuevas
  agregadas al mismo archivo (`sales_territories`, `customer_portfolios`,
  `customer_ownerships`, `portfolio_assignments`, `customer_segments`,
  `customer_segment_memberships`, `customer_tags`,
  `customer_tag_assignments`) + sus índices. `crm_audit_log` **no** ganó
  columnas FK dedicadas para estas 8 entidades (a diferencia de CRM-6, que
  sí agregó `activity_id`/`task_id`/`note_id`) — con 8 entidades más
  hubiera significado 8 columnas nulables adicionales en una tabla ya
  compartida; en su lugar, el `before_json`/`after_json` genéricos que
  `CRMAuditRepository.record()` ya soportaba desde CRM-4 cargan
  `{"entity_type": ..., "entity_id": ...}`. Decisión explícita, no
  descuido.
- **`migrations/standalone/190_crm_segmentation_bounded_context_schema.py`**
  — número verificado contra `engine.py` y el directorio de migraciones
  dos veces (al inicio de la fase de diseño y de nuevo inmediatamente
  antes de crear el archivo — 190-199 libre, 200 ya reclamado por una
  sesión concurrente para `uuid_identity_cutover`). Solo `CREATE TABLE IF
  NOT EXISTS` — sin `ALTER TABLE`, porque son tablas nuevas, no columnas
  nuevas en una tabla existente. Registrada en `migrations/engine.py`.
  Bootstrap completo verificado: 583 tablas totales, las 8 nuevas
  presentes.
- **`backend/infrastructure/db/repositories/crm/`** — 8 repositorios
  nuevos, cableados en `CRMUnitOfWork` (`territories`, `portfolios`,
  `ownerships`, `portfolio_assignments`, `segments`, `segment_memberships`,
  `tags`, `tag_assignments`). Los dos repositorios append-only
  (`CustomerOwnershipRepository`, `PortfolioAssignmentRepository`) usan
  `ORDER BY created_at DESC, id DESC` en `get_latest()` desde el día uno —
  aplicando directamente la lección del bug de CRM-9, no repitiéndolo.

## Aplicación (extiende `backend/application/crm/`)

- **`permissions.py`** — `PORTFOLIOS_ASSIGN` (única adición retroactiva).
- **`use_cases/territory_use_cases.py`** — `CreateSalesTerritoryUseCase`,
  `DeactivateSalesTerritoryUseCase` (`TERRITORIES_MANAGE`, solo `crm`), y
  `AssignCustomerTerritoryUseCase` (cruza a `customers` — mismo patrón de
  conexión compartida y commit/rollback manual que
  `ConvertLeadUseCase`/`AnonymizeCustomerUseCase`).
- **`use_cases/portfolio_use_cases.py`** — `CreateCustomerPortfolioUseCase`,
  `DeactivateCustomerPortfolioUseCase` (`PORTFOLIOS_MANAGE`), y
  `AssignCustomerPortfolioUseCase` (`PORTFOLIOS_ASSIGN`; exige motivo vía
  SoD solo si ya existe un `PortfolioAssignment` previo para ese cliente).
- **`use_cases/ownership_use_cases.py`** — `AssignCustomerOwnerUseCase`,
  el único caso de uso que cruza a `customers` en este archivo. Segundo
  consumidor real de `enforce_ownership_reassignment_justified()` (junto
  con el de carteras, ambos primeros consumidores desde CRM-2).
- **`use_cases/segment_use_cases.py`** — `CreateCustomerSegmentUseCase`,
  `DeactivateCustomerSegmentUseCase` (`SEGMENTS_CREATE`/`SEGMENTS_EDIT`),
  `AddCustomerToSegmentUseCase` (`SEGMENTS_ASSIGN`, rechaza membresía
  activa duplicada), `RemoveCustomerFromSegmentUseCase` (`SEGMENTS_REMOVE`).
- **`use_cases/tag_use_cases.py`** — `CreateCustomerTagUseCase`,
  `DeactivateCustomerTagUseCase` (`TAGS_CREATE`/`TAGS_EDIT`),
  `AssignCustomerTagUseCase` (`TAGS_ASSIGN`, rechaza duplicado activo),
  `RemoveCustomerTagUseCase` (`TAGS_REMOVE`).
- **`queries/customer_ownership_query_service.py`** — nombrado
  explícitamente en §57. Flat `CUSTOMER_OWNER_VIEW` (sin eje OWN/TEAM,
  mismo criterio sin-sufijo que `CRMActivityQueryService` de CRM-6).
- **`queries/customer_portfolio_query_service.py`** — nombrado
  explícitamente en §57. `list_current_members()` resuelve "miembro
  actual" en Python (un `get_latest()` por cliente distinto) en vez de un
  sub-select correlacionado en SQL — mismo criterio de simplicidad que ya
  se usó para `FieldVisibility` en CRM-8.
- **`queries/customer_segmentation_query_service.py`** — **no** nombrado
  individualmente en §57 (que no separa segmentos de etiquetas en dos
  servicios); se consolidó uno solo para ambos, mismo criterio de
  consolidación que CRM-9 aplicó a consentimiento+preferencia. Territorio
  queda deliberadamente fuera: es un campo plano de `Customer`, ya
  alcanzable desde el query service de perfil de Clientes.

## Verificación

```bash
python -m pytest tests/unit/crm/test_segmentation_ownership_entities.py \
  tests/integration/crm/test_segmentation_ownership_repositories.py \
  tests/integration/crm/test_segmentation_ownership_application.py \
  tests/architecture/test_customers_crm_*.py -v
# 58 passed (segmentación) + 21 passed, 1 skipped (guardrails)
```

- 58 tests nuevos (26 unitarios de dominio — catálogos + append-only
  capture/remove — y 32 de integración con SQLite real: repositorios
  incluido el desempate `get_latest()`, y aplicación incluyendo el split
  assign/reassign de propietario con verificación de qué permiso exacto
  se consultó, el requisito de motivo SoD en reasignación de cartera y de
  propietario, y la sincronización cross-context con `Customer.
  account_owner_user_id`/`territory_id` en ambos sentidos, éxito y
  rollback en fallo).
- Los 22 guardrails de CRM-1 se re-ejecutaron completos y siguieron en
  verde sin ajustes.
- 630 tests de `tests/unit/{customers,crm,customer_credit,customer_privacy,
  customer_service}/` + sus contrapartes de integración pasan juntos.
- Paridad de catálogo verificada explícitamente: `ALL_CRM_PERMISSIONS` ==
  `CANONICAL_MODULE_PERMISSIONS["CRM"]` (con el prefijo `CRM.` normalizado),
  sin faltantes en ninguna dirección.
- Sintaxis limpia en todo lo tocado por esta fase; bootstrap completo de
  migraciones verificado (583 tablas, las 8 nuevas presentes).

## Pendiente (próximas fases)

- **CRM-11 (Calidad/duplicados/fusión):** §45-46, explícitamente fuera de
  alcance aquí. `CustomerMergeRecord` deberá resolver ownership/cartera/
  segmentos/etiquetas del cliente fusionado — consumidor natural de los
  repositorios de esta fase.
- **CRM-12 (Customer 360):** consumidor natural de
  `CustomerOwnershipQueryService`/`CustomerPortfolioQueryService`/
  `CustomerSegmentationQueryService` para la tab "Segmentación" del
  expediente.
- **CRM-13 (Integraciones/BI):** el flujo real de `RULE_BASED`/
  `ANALYTICS_GENERATED` (BI evalúa, CRM registra vía
  `AddCustomerToSegmentUseCase`) queda como contrato definido pero sin
  integración real todavía — ningún job externo lo llama aún.
- `SEGMENTS_VIEW`/`TAGS_VIEW`/`TERRITORIES_VIEW`/`PORTFOLIOS_VIEW`/
  `CUSTOMER_OWNER_VIEW` ya tienen consumidor (los query services de esta
  fase); las acciones de escritura de catálogo (`SEGMENTS_EDIT` más allá
  de desactivar, p. ej. renombrar) quedan mínimas a propósito — ampliarlas
  es trabajo de UI (CRM-14+), no de esta fase.
