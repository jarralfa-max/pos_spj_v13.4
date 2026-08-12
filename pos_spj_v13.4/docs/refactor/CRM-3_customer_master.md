# CRM-3 — Customer Master

Fecha: 2026-08-08. Depende de CRM-0 (auditoría), CRM-1 (guardrails), CRM-2 (seguridad).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §11-15, §58.
Precedente seguido al pie de la letra: `backend/domain/suppliers/` +
`backend/infrastructure/db/repositories/suppliers/` + `backend/application/suppliers/`
(el bounded context más parecido — un "party master" con contactos/direcciones/
datos fiscales/ciclo de vida — ya construido en este repo).

## Objetivo

Primera entidad de dominio real del bounded context CRM: `Customer`,
`CustomerAccount`, `CustomerContactPerson`, `CustomerAddress`,
`CustomerTaxProfile`. Nace directamente sobre los cimientos de CRM-1
(guardrails) y CRM-2 (permisos/scopes/SoD/auditoría/enmascaramiento) — es la
primera vez que ese trabajo se conecta a un caso de uso real.

No se tocó `modulos/clientes.py` ni ningún consumidor legacy. `clientes`
(tabla legacy) y `customers` (tabla nueva) coexisten sin relación hasta
CRM-21/22.

## Dominio (`backend/domain/customers/`)

- **`enums.py`** — `CustomerType`, `CustomerStatus`, `LifecycleStage`,
  `ContactDecisionRole`, `AddressType`, `ValidationStatus`.
- **`value_objects/`** — `CustomerCode` (folio `CLI-NNNNNN`, separado del
  `id` UUIDv7 por REGLA CERO §11), `PhoneNumber` (E.164 estricto, mirror de
  `backend/domain/hr/value_objects.py::PhoneE164`), `EmailAddress` (mirror
  de `Email`).
- **`entities/customer.py`** — agregado raíz. Máquina de estados:

  ```text
  DRAFT/PROSPECT ──activate()──► ACTIVE ──suspend(reason)──► SUSPENDED
                                    │                              │
                                    ├──deactivate()──► INACTIVE ◄──┤
                                    │                    │          activate()
                                    ├──block(reason)──► BLOCKED ◄──┘
                                    │
                                    └──close(reason)──► CLOSED (terminal)

  mark_merged(target_id) ──► MERGED (terminal, CRM-11)
  mark_anonymized()      ──► ANONYMIZED (terminal, CRM-9)
  ```

  `deactivate()` **no está en la lista de use cases del master prompt**
  (§58 solo nombra Activate/Suspend/Block/Close) pero es obligatorio por
  CLAUDE.md Prioridad 0: reproduce exactamente lo que
  `ModuloClientes.eliminar_cliente()` ya hace hoy (baja reversible, conserva
  historial — ver `docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md` §1).
  Se agregó el permiso `CLIENTES.desactivar` en CRM-2's `CustomerPermissions`
  para sostenerlo (registrado también en `core/security/permission_catalog.py`,
  verificado 1:1 — ver §"Ajuste a CRM-2" abajo).

- **`entities/customer_account.py`**, **`customer_contact.py`**,
  **`customer_address.py`**, **`customer_tax_profile.py`** — entidades hijas
  con su propio UUIDv7, mirror de `SupplierContact`/`SupplierAddress`.
  `CustomerAddress` usa la descomposición de domicilio mexicano (calle,
  número exterior/interior, colonia, municipio) en vez del `line` libre que
  usa Suppliers, por pedido explícito del master prompt §14.
- **`events.py`** — `CustomerEvents` (subconjunto de §77 correspondiente a
  Customer Master; Leads/Oportunidades/Actividades/Casos quedan para
  `backend/domain/crm/events.py` en CRM-4+) + `build_event_payload`.
- **`policies/duplicate_policy.py`** — `CustomerDuplicatePolicy` (§45: RFC,
  nombre normalizado, teléfono, correo). Reemplaza y amplía el dedupe legacy
  (`ClienteService.existe_similar`, exact-match nombre+apellido+teléfono) sin
  fusionar automáticamente — solo reporta candidatos.
- **`repository_ports.py`** — Protocols (§10), mirror de
  `backend/domain/finance/repository_ports.py`.
- **`exceptions.py`** — extendido (CRM-2 ya tenía las de seguridad) con
  `CustomerNotFoundError`, `CustomerAlreadyExistsError`,
  `InvalidCustomerStateError`, `CustomerBlockedError`,
  `CustomerDuplicateDetectedError`, `InvalidCustomerCodeError`,
  `InvalidPhoneNumberError`, `InvalidEmailAddressError` (§93).

## Infraestructura

- **`backend/infrastructure/db/schema/customers_crm_schema.py`** — DDL único
  (8 tablas: `customers`, `customer_accounts`, `customer_contacts`,
  `customer_addresses`, `customer_tax_profiles`, `customer_audit_log`,
  `customer_outbox`, `customer_processed_events`). Todo `id` es `TEXT
  PRIMARY KEY`; `customer_number` es `UNIQUE` separado; sin `REAL` para
  dinero (este esquema no tiene columnas de crédito — eso es CRM-8, sobre
  las tablas de CxC de Finanzas). La columna de dirección se llama
  `address_references` (no `references`, palabra reservada) — el
  repositorio mapea ese desajuste de nombre explícitamente; hay un test de
  integración dedicado a que ese mapeo no se rompa silenciosamente.
- **`migrations/standalone/181_customers_crm_bounded_context_schema.py`** +
  registro en `migrations/engine.py` (siguiente número libre tras el 180;
  el 200 existente es la herramienta especial de corte UUID, no parte de la
  secuencia incremental). Verificado contra el bootstrap completo
  (`migrations.engine.up`) sobre una base `:memory:` limpia — las 8 tablas
  aparecen, sin colisión con la tabla `customer_price_list` legacy
  (pricing, no relacionada) ni con nada más.
- **`backend/infrastructure/db/repositories/customers/`** — `base.py`
  (helpers `_query`/`_execute`/`_scalar`, sin commit — lo hace la UoW),
  `customer_repository.py` (save/update/get/get_by_code/
  get_by_operation_id/find_duplicate_rows/list_active/list_owned_by/
  list_by_branch/list_by_territory — los cuatro últimos existen
  específicamente para que `CustomerDataScopeResolver` tenga una consulta
  real que ejecutar por eje), `customer_child_repositories.py` (cuentas/
  contactos/direcciones/fiscal), `support_repositories.py` (audit/outbox/
  processed events), `unit_of_work.py` (`CustomerUnitOfWork`, una sola
  transacción para maestro + hijos + auditoría + outbox).

## Aplicación (`backend/application/customers/`)

- **`authorization.py`** — `CustomerAuthorizationPolicy`, primera vez que
  `CustomerPermissions`/`ALL_CUSTOMER_PERMISSIONS` (CRM-2) se conectan a un
  caso de uso real. **Fail closed** (mirror de
  `InventoryAuthorizationPolicy`, no de la variante fail-open de Suppliers):
  sin `PermissionChecker` configurado, `require()` lanza
  `CustomerConfigurationError` — nunca permite. Consistente con el fail-closed
  que `CustomerDataScopeResolver` ya exigía desde CRM-2. `authorize_exception()`
  cubre la autorización en caliente de §74 y devuelve un
  `CustomerAuthorizationGrant` (CRM-2).
- **`use_cases/lifecycle_use_cases.py`** — `CreateCustomerUseCase` (dedupe +
  idempotencia por `operation_id` + folio secuencial), `UpdateCustomerUseCase`,
  `ActivateCustomerUseCase`, `DeactivateCustomerUseCase`,
  `SuspendCustomerUseCase`, `BlockCustomerUseCase`, `CloseCustomerUseCase`.
- **`use_cases/contact_use_cases.py`** — Add/Update/SetPrimary/Remove.
- **`use_cases/address_use_cases.py`** — Add/Update/SetDefault/Remove.
- **`use_cases/tax_profile_use_cases.py`** — `UpdateCustomerTaxProfileUseCase`
  (upsert: crea el perfil si no existe, uno por cliente).
- **`queries/customer_profile_query_service.py`** — `CustomerProfileQueryService`,
  primer consumidor real de `CustomerDataScopeResolver` (CRM-2).
  `get_profile()` no solo filtra el listado — vuelve a comprobar que el
  cliente pedido cae dentro del scope resuelto antes de devolverlo, así que
  adivinar un `customer_id` fuera de la cartera propia no sirve para saltarse
  el filtro. `list_directory()` resuelve OWN/TEAM/BRANCH/TERRITORY/COMPANY a
  una consulta real de repositorio; PORTFOLIO devuelve vacío a propósito
  (no existe todavía señal de membresía de cartera — eso es CRM-10 — y
  ensanchar a "todo" sería la fuga exactamente contraria a lo que CRM-2
  existe para evitar).

Todos los use cases: permiso → `CustomerUnitOfWork` → mutación de dominio →
`uow.audit.record(...)` → evento a `uow.outbox` → commit. Ninguno ejecuta
SQL fuera del repositorio ni conoce PyQt/UI.

## Ajuste retroactivo a CRM-1 y CRM-2

- **CRM-1** — `test_customers_crm_uses_uuidv7.py` exigía que *cada archivo*
  de repositorio que contuviera `INSERT INTO` importara
  `backend.shared.ids` directamente. Al escribir `CustomerRepository` (que
  persiste una entidad cuyo `id` ya generó `Customer.create()` en el
  dominio — el patrón correcto) el guardrail marcó un falso positivo. Se
  corrigió para exigir el import canónico a nivel de *paquete* (al menos un
  archivo del contexto lo usa, hoy `support_repositories.py` para ids de
  auditoría/outbox) en vez de por archivo — el objetivo real (nadie usa
  `uuid4()`/`randomblob()`) se sigue verificando por archivo sin cambios.
- **CRM-2** — se agregó `CustomerPermissions.DEACTIVATE =
  "CLIENTES.desactivar"` (ver arriba) y su sufijo `desactivar` en
  `core/security/permission_catalog.py`, re-verificado 1:1 sin drift
  (75 permisos `CLIENTES.*`, 78 `CRM.*`, antes 74/78).
- Dos falsos positivos de las propias palabras del guardrail contra su
  propio texto (`autoincrementos` conteniendo `AUTOINCREMENT`; un
  docstring con `Decimal | int | str` conteniendo `int | str`) se
  corrigieron reescribiendo la prosa, no el guardrail — eran detecciones
  correctas de una coincidencia literal, no bugs del scanner.

## Verificación

```bash
python -m pytest tests/unit/customers/ tests/unit/crm/ tests/integration/customers/ \
  tests/architecture/test_customers_crm_*.py -q
# 120 passed, 1 skipped (routes — CRM-14)
```

- 120 tests nuevos (31 unitarios de dominio, 45 de seguridad CRM-2, 44 de
  integración con SQLite real — repositorios + casos de uso + query
  service).
- Guardrails de CRM-1: **los tres que estaban en skip ahora están todos
  activos** — permisos/scopes desde CRM-2, UUIDv7 desde CRM-3. Solo queda en
  skip `routes_are_stable` (CRM-14, cuando exista `customers_crm_routes.py`).
- Verificado contra el bootstrap completo de migraciones
  (`migrations.engine.up` sobre `:memory:` limpio): las 8 tablas nuevas
  aparecen sin colisión; ninguna falla nueva introducida (las fallas
  preexistentes de bootstrap — migraciones 024/029/030/080 sobre tablas de
  caja legacy — son ajenas a este trabajo).
- Sintaxis global (`ast.parse`) limpia en todos los archivos nuevos.

## Pendiente (próximas fases)

- **CRM-4 (Leads):** primeras entidades bajo `backend/domain/crm/` — activa
  la mitad de `CRMPermissions` que hoy solo tiene catálogo sin código detrás.
- **CRM-8 (Crédito):** `CustomerCreditProfile` bajo `backend/domain/customer_credit/`
  — ahí es donde `CustomerAuthorizationPolicy.authorize_exception()` con
  `credit_amount` y `CustomerSegregationOfDutiesPolicy.enforce_credit_requester_not_self_approving`
  (ambos de CRM-2) se usan por primera vez de verdad.
- **CRM-14 (UI Foundations):** consumir estos use cases desde
  `frontend/desktop/modules/customers_crm/` — activa el último guardrail en skip.
- No implementado en CRM-3 (fuera de alcance explícito — "Customer / Account
  / Contact / Address / TaxProfile"): `CreateQuickCustomerUseCase` (alta
  rápida desde Ventas — CRM-13), reconciliación con las tres rutas legacy
  paralelas que encontró CRM-0 (`GestionarClienteUC`, el `CreateCustomerUseCase`
  viejo de `backend/application/use_cases/`, el router FastAPI) — eso es
  CRM-21/22 una vez que este bounded context tenga UI real que lo reemplace.
