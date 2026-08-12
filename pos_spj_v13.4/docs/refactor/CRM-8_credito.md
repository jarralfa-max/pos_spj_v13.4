# CRM-8 — Crédito del Cliente / CxC

Fecha: 2026-08-12. Depende de CRM-0 (auditoría), CRM-1 (guardrails —
`customer_credit` ya existía como paquete vacío con la docstring
"CustomerCreditProfile, credit workflow states. See master prompt §37-40"),
CRM-2 (seguridad — `CustomerPermissions.CREDIT_*` ya existían sin
consumidor, así como `CustomerSegregationOfDutiesPolicy.
enforce_credit_requester_not_self_approving()` y
`CustomerAuthorizationPolicy.authorize_exception()`/
`CustomerAuthorizationGrant`, construidos en CRM-2 específicamente para
esta fase y sin llamador hasta ahora), CRM-3 (Customer Master — el
`customer_id` que enlaza cada perfil), CRM-7 (precedente estructural: el
segundo sub-bounded-context sibling que CRM-1 dejó vacío y esta iniciativa
llena con código real).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §37-40.

## Decisión estructural: reutiliza el stack de autorización de `customers`, no el de `crm`

Los permisos `CREDIT_*` viven bajo el namespace `CLIENTES.credito.*`
(`CustomerPermissions`, no `CRMPermissions`) — el crédito es una faceta del
expediente del cliente, no de la relación comercial (leads/oportunidades).
Por eso `backend/application/customer_credit/` importa directamente
`CustomerAuthorizationPolicy`/`CustomerPermissions` de
`backend.application.customers` y
`CustomerSegregationOfDutiesPolicy`/`FieldVisibility` de
`backend.domain.customers` — mismo criterio de reutilización cruzada que
CRM-7 ya estableció (ahí contra el stack de `crm`), aplicado ahora contra
el stack de `customers`. Las excepciones de permiso/alcance/SoD siguen
siendo `CustomerPermissionDeniedError`/`CustomerScopeError`/
`CustomerSegregationOfDutiesError`/`InvalidAuthorizationError` — este
bounded context no define una jerarquía paralela.

## Decisiones de alcance (documentadas, no adivinadas)

- **`current_exposure`/`available_credit` NO son columnas de
  `CustomerCreditProfile`.** §40 es explícito: "CxC: Finanzas es dueño de
  documentos/vencimientos/pagos/saldo/reversos... no crear ledger
  financiero paralelo." Nada en este bounded context registra una venta o
  un pago, así que una columna `current_exposure` aquí se volvería
  obsoleta en el momento en que Ventas registre una venta o Finanzas un
  pago. `CustomerAccountsReceivableSummaryQuery` (capa de aplicación) los
  calcula en vivo, de solo lectura, contra `cuentas_por_cobrar` (tabla de
  Finanzas) — nunca los persiste. Mismo criterio de "derivado, no
  almacenado" que CRM-6/7 ya aplicaron a OVERDUE/`SLABreachStatus`.
- **No hay estado `REJECTED`.** La lista de estados literal de §37-40
  (`NOT_CONFIGURED, PENDING_APPROVAL, UNDER_REVIEW, AUTHORIZED, SUSPENDED,
  BLOCKED, CLOSED`) no lo incluye — `reject()` transiciona a `CLOSED` con
  `close_reason` registrando el motivo del rechazo.
- **`NOT_CONFIGURED` nunca se persiste.** Representa "el cliente no tiene
  fila de perfil todavía" — lo reporta la capa de consulta cuando el
  repositorio no encuentra ninguna fila, no un valor de estado real
  guardado (documentado en `CreditProfileStatus`).
- **Gap de identidad conocido, no oculto**: `cuentas_por_cobrar.cliente_id`
  fue creada contra la tabla legacy `clientes` (entera), no contra la
  nueva tabla `customers` (UUIDv7) de CRM-3 — el propio esquema de
  `customers_crm_schema.py` documenta "sin compatibilidad legacy" como
  decisión deliberada. `CustomerAccountsReceivableSummaryQuery` consulta
  correctamente por el `customer_id` nuevo; hasta que CRM-21/22 unifique
  ambas identidades, esto devuelve exposición cero para clientes que solo
  existen en el modelo nuevo — es un reflejo preciso del dato actual, no
  un fallback silencioso. Documentado explícitamente en el docstring de la
  query, no descubierto por el usuario más tarde.
- **`ReopenCustomerCreditUseCase` no está en la lista literal de §37-40**
  pero el permiso `CREDIT_REOPEN` ya existía en el catálogo de CRM-2 sin
  consumidor — mismo criterio de "no dejar un permiso huérfano" aplicado en
  CRM-6/7. Se construyó.
- **Retroactivo a CRM-2**: se agregó `CREDIT_CLOSE`
  (`CLIENTES.credito.cerrar`) — `CloseCustomerCreditUseCase` sí está
  nombrado literalmente en §37-40, pero el catálogo original no tenía un
  permiso de "cerrar" distinto de `CREDIT_LIMIT_EDIT` (que es sobre el
  monto del límite, no sobre el ciclo de vida del perfil). Mismo patrón que
  `TASKS_RESCHEDULE` (CRM-6) / `SLA_MANAGE` (CRM-7). Verificado 1:1 sin
  drift: 74→75 permisos de `CustomerPermissions`.
- **`CreditSaleEligibilityPolicy` no es llamada desde POS.** §38: "Nunca
  autorizar crédito directo desde POS." Este bounded context expone
  `CheckCreditSaleEligibilityUseCase` (lectura, sin efectos) para que
  Ventas/Finanzas lo invoque antes de registrar una venta a crédito — CRM-8
  nunca inicia ni registra la venta en sí.

## Dominio (`backend/domain/customer_credit/`)

- **`enums.py`** — `CreditProfileStatus` (7 estados), `CreditRiskLevel`
  (LOW/MEDIUM/HIGH/VERY_HIGH — no enumerado literalmente en §37-40, escala
  convencional documentada como tal).
- **`entities/customer_credit_profile.py`** — `CustomerCreditProfile`,
  agregado raíz. Flujo completo: `request()` → `review()` → `approve()`/
  `reject()` → `update_limit()` (solo en AUTHORIZED) → `suspend()`/
  `block()` → `reopen()` → `close()`. `version` se incrementa en cada
  mutación (optimistic-concurrency-friendly, campo nombrado explícitamente
  en §37-40).
- **`policies/credit_sale_eligibility_policy.py`** —
  `CreditSaleEligibilityPolicy.evaluate()`, dominio puro, implementa los
  siete chequeos de §38 que le corresponden al dominio (no público, perfil
  autorizado, límite > 0, crédito disponible, documentos vigentes,
  sucursal permitida) — "cliente identificado" y "permiso" son
  responsabilidad del llamador/capa de aplicación. Devuelve **todas** las
  violaciones encontradas, nunca solo la primera ("sin fallback
  silencioso").
- **`events.py`** — `CustomerCreditEvents` (10 eventos) +
  `build_event_payload()` propio.
- **`repository_ports.py`** — puerto único, `CustomerCreditProfileRepositoryPort`.
- **`exceptions.py`** — solo errores propios (`InvalidCustomerCreditStateError`,
  etc.) — sin duplicar los de autorización/SoD de `customers` (ver arriba).

## Infraestructura

- **`backend/infrastructure/db/schema/customer_credit_schema.py`** —
  archivo nuevo, 4 tablas: `customer_credit_profiles` (`UNIQUE(customer_id)`
  — un perfil por cliente), `customer_credit_audit_log` (incluye
  `authorized_by_user_id` como columna propia desde el diseño inicial —
  a diferencia de las extensiones retroactivas de CRM-5/6/7 a tablas de
  auditoría ya existentes, esta tabla es nueva, así que no hizo falta un
  `ALTER TABLE` después), `customer_credit_outbox`,
  `customer_credit_processed_events`. **No define ninguna tabla CxC** —
  verificado por `test_customers_crm_does_not_duplicate_cxc.py` (CRM-1),
  que ya escaneaba este sub-bounded-context.
- **`migrations/standalone/188_customer_credit_bounded_context_schema.py`**
  — número verificado contra `engine.py` y el directorio
  `migrations/standalone/` inmediatamente antes de crear el archivo
  (188 libre; otra sesión concurrente ya había tomado 187 para
  `meat_processing`, sin relación). Registrada en `migrations/engine.py`.
  Verificado contra el bootstrap completo: 568 tablas totales.
- **`backend/infrastructure/db/repositories/customer_credit/`** — un
  repositorio (`CustomerCreditProfileRepository`) + `support_repositories.py`
  + `unit_of_work.py` + `base.py`, mirror exacto de la capa CRM-7
  equivalente.

## Aplicación (`backend/application/customer_credit/`)

- **`use_cases/customer_credit_use_cases.py`** —
  `RequestCustomerCreditUseCase` (idempotente por `operation_id`; rechaza
  una segunda solicitud si el cliente ya tiene perfil),
  `ReviewCustomerCreditUseCase`, `RejectCustomerCreditUseCase`,
  `UpdateCustomerCreditLimitUseCase`, `SuspendCustomerCreditUseCase`,
  `BlockCustomerCreditUseCase`, `ReopenCustomerCreditUseCase`,
  `CloseCustomerCreditUseCase`.

  **`ApproveCustomerCreditUseCase`** — primer consumidor real de
  `CustomerSegregationOfDutiesPolicy.
  enforce_credit_requester_not_self_approving()` (CRM-2, sin llamador
  hasta ahora): compara `profile.requested_by_user_id` contra el
  `actor_user_id` que aprueba y falla con `error_code=
  "SEGREGATION_OF_DUTIES"` si coinciden — nunca antes ejercitado en este
  código base.

  **`UpdateCustomerCreditLimitUseCase(override=True)`** — primer consumidor
  real de `CustomerAuthorizationPolicy.authorize_exception()`/
  `CustomerAuthorizationGrant` (CRM-2, sin llamador hasta ahora): un
  aumento "extraordinario" de límite requiere `CREDIT_LIMIT_OVERRIDE` y un
  `requested_by_user_id` distinto del autorizador — la invariante vive en
  el propio value object (`authorized_by != requested_by`), reforzada dos
  veces (política y VO). El caso de uso nunca deja escapar la excepción de
  dominio cruda: la captura y la convierte en un `CustomerCreditResult`
  fallido, igual que cualquier otro fallo de permiso en este bounded
  context.
- **`use_cases/check_credit_sale_eligibility_use_case.py`** —
  `CheckCreditSaleEligibilityUseCase`, el punto de entrada de solo lectura
  que Ventas/Finanzas debe llamar antes de una venta a crédito. Combina
  `CustomerCreditProfile` + `CustomerAccountsReceivableSummaryQuery` (para
  `available_credit` en vivo) + `CreditSaleEligibilityPolicy`.
- **`queries/customer_accounts_receivable_summary_query.py`** —
  `CustomerAccountsReceivableSummaryQuery`, lee `cuentas_por_cobrar`
  directamente (parametrizado, de solo lectura). Como esa tabla no tiene
  columna de fecha de vencimiento, la calcula como
  `fecha + payment_terms_days` (del perfil de crédito) — mismo criterio
  "derivado, no almacenado". Suma cada `saldo_pendiente` como `Decimal`
  fila por fila (nunca `SUM()` de SQL sobre `REAL`, para no arrastrar
  imprecisión de punto flotante).
- **`queries/customer_credit_query_service.py`** —
  `CustomerCreditQueryService.get_summary()`, primer consumidor real de
  `FieldVisibility`/`mask()` (CRM-2) para montos monetarios:
  `CREDIT_VIEW` solo → montos enmascarados (`MASKED`);
  `CREDIT_VIEW_SUMMARY` → parcialmente visibles (últimos 4 dígitos);
  `CREDIT_VIEW_SENSITIVE` → visibles completos. Sin eje OWN/TEAM (mismo
  criterio de permiso plano que CRM-6 aplicó a Actividades/Tareas/Notas).

## Verificación

```bash
python -m pytest tests/unit/customer_credit/ tests/integration/customer_credit/ tests/architecture/test_customers_crm_*.py -q
# 80 passed, 1 skipped (routes — CRM-14)
```

- 53 tests nuevos (25 unitarios de dominio — lifecycle de
  `CustomerCreditProfile`, `CreditSaleEligibilityPolicy` con sus siete
  reglas — y 28 de integración con SQLite real, incluyendo una tabla
  `cuentas_por_cobrar` legacy real para probar la query de CxC:
  repositorios, segregación de deberes solicitante≠aprobador, el flujo de
  autorización en caliente con auditoría, transiciones de ciclo de vida
  completas, enmascaramiento de montos, y el gate de elegibilidad de venta
  a crédito).
- Los 22 guardrails de CRM-1 se re-ejecutaron completos (primera vez con
  código real en `customer_credit` bajo esos escaneos) y siguieron en
  verde sin ajustes, incluido el guardrail anti-CxC-paralelo.
- 495 tests de `tests/unit/customers/` + `tests/integration/customers/` +
  `tests/unit/crm/` + `tests/integration/crm/` +
  `tests/unit/customer_service/` + `tests/integration/customer_service/` +
  `tests/unit/customer_credit/` + `tests/integration/customer_credit/`
  pasan juntos.
- Sintaxis global limpia; bootstrap completo de migraciones verificado
  (568 tablas).

## Pendiente (próximas fases)

- **CRM-9 (Privacidad):** siguiente sub-bounded-context vacío que CRM-1
  anticipó (`customer_privacy`) — el último de los cinco.
- **CRM-21/22:** unificación de identidad `clientes` (legacy) ↔
  `customers` (CRM-3) — cuando aterrice, `CustomerAccountsReceivableSummaryQuery`
  empezará a ver exposición real para clientes creados bajo el modelo
  nuevo sin cambios de código.
- No implementado: envío de `CustomerCreditEvents` a un motor de reglas
  automatizado (p. ej. `SLA_BREACHED`→escalamiento de crédito, similar a
  `CRMAutomationRule` de §56) — CRM-15+.
- `CREDIT_EXPORT`/`CREDIT_HISTORY_VIEW` no tienen un caso de uso propio
  todavía (exportación/reporting es infraestructura de UI, no lógica de
  dominio) — candidato natural para CRM-14+.
