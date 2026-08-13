# CRM-13 — Integraciones: Ventas, Cotizaciones, Pedidos, Delivery, WhatsApp, Fidelidad, Finanzas, BI

Fecha: 2026-08-13. Extiende `customers` y `crm` (no crea un sexto
sub-bounded-context — `CRM_SUBCONTEXTS` en
`tests/architecture/customers_crm_guardrails.py` sigue fija en cinco).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §49-55.

## Hallazgo previo a escribir código: el mismo gap de identidad cruza casi toda la superficie

Antes de tocar código se investigaron en paralelo los ocho módulos externos
que §49-55 nombra. El hallazgo dominante: **Ventas, Cotizaciones, Pedidos,
Delivery, WhatsApp y Fidelidad comparten el mismo problema no resuelto** ya
documentado una vez para Finanzas (`CustomerAccountsReceivableSummaryQuery`,
CRM-8) — sus tablas usan el `clientes.id` legacy (o, en el caso de
`delivery_orders`, una TERCERA identidad incompatible: `cliente_id
INTEGER`), nunca el `customers.id` UUIDv7 de este bounded context. CRM-0 ya
había señalado esto como un gap conocido; esta fase confirma que no es
exclusivo de Finanzas — cruza prácticamente toda la superficie de
"Integraciones" — y aplica exactamente la misma disciplina que CRM-8 ya
estableció: construir la lectura real y correcta (consumible directamente
por `customer_id`, probada, lista para producción), documentar el gap sin
fabricar un puente falso, y diferir la reconciliación a CRM-21/22.

Segundo hallazgo, aplicando la lección de CRM-12 ("verificar si ya existe
antes de construir"): **`CustomerCreditEligibilityQuery` (§49) ya existía**
como `CheckCreditSaleEligibilityUseCase` (`backend/application/
customer_credit/use_cases/check_credit_sale_eligibility_use_case.py`,
CRM-8) — su propio docstring desde entonces citaba textualmente el nombre
que §49 usa. Se encontró, se verificó con una prueba nueva, y NO se
reconstruyó — el permiso retroactivo `CREDIT_ELIGIBILITY_CHECK` que se
había agregado especulativamente antes de encontrarlo fue removido.

## Qué se construyó, sub-tema por sub-tema

### Ventas (§49)

- **`Customer.last_purchase_at`/`Customer.purchase_count`** (nuevos campos,
  migración 192 vía `ALTER TABLE` idempotente + `_DDL` actualizado para
  instalaciones nuevas) + **`Customer.record_sale_activity(occurred_at)`**/
  **`record_sale_cancelled()`** (`backend/domain/customers/entities/
  customer.py`): incrementa/decrementa el contador, y avanza
  `lifecycle_stage` (PROSPECT/LEAD/QUALIFIED/LOST → CUSTOMER; INACTIVE/
  AT_RISK → REPEAT_CUSTOMER; CUSTOMER con 2ª compra → REPEAT_CUSTOMER) sin
  retroceder nunca un estado ya "mejor". Cancelar una venta NUNCA revierte
  `lifecycle_stage` (una cancelación no es evidencia de que la relación
  empeoró) ni intenta recalcular `last_purchase_at` desde el historial (este
  bounded context no es dueño del historial de ventas).
- **`RecordCustomerSaleActivityUseCase`/`RecordCustomerSaleCancelledUseCase`**
  (`backend/application/customers/use_cases/sales_integration_use_cases.py`):
  el primer consumidor real de `CustomerProcessedEventRepository`
  (`customer_processed_events`, tabla construida en CRM-3, sin consumidor
  hasta ahora — el mismo patrón "CRM-N la construye, CRM-M finalmente la
  usa" ya visto con la política de SoD/hot-auth/`search_lookup`).
  Disparados por un evento de OTRO bounded context, no por un usuario — sin
  `actor_user_id`/chequeo de permiso, a diferencia de cada otro caso de uso
  de este paquete.
- **`backend/application/customers/integrations/sales_event_handlers.py`**
  (`handle_sale_completed`/`handle_sale_cancelled`): traduce el payload
  crudo de `VENTA_COMPLETADA`/`VENTA_CANCELADA` (`core/events/
  event_bus.py`/`core/services/sales_service.py`) a los casos de uso
  anteriores. **Deliberadamente NO conectado a `core/events/wiring.py`** —
  ver sección de decisiones abajo.
- **`CustomerCommercialEligibilityQuery`** (`backend/application/customers/
  queries/customer_commercial_eligibility_query.py`, nuevo permiso
  `CLIENTES.elegibilidad_comercial.verificar`): elegibilidad a nivel
  Customer Master (estatus), independiente de crédito.
- Sin cambios a `CheckCreditSaleEligibilityUseCase` (ya cubría §49's
  `CustomerCreditEligibilityQuery`) — solo se le agregó una prueba de
  integración nueva confirmando que funciona contra un cliente creado por
  este bounded context.
- **No existe `SALE_RETURNED`** en `core/events/event_bus.py`/
  `domain_events.py` — no hay nada a lo que suscribirse; sub-caso diferido,
  no fabricado.

### Cotizaciones (§49) — diferido por completo

Investigación: `create_quote_use_case.py`/`approve_quote_use_case.py`/
`convert_quote_to_sale_use_case.py` (`backend/application/use_cases/`) son
`DelegatingUseCase` vacíos — sin handler inyectado en ningún lugar del
repositorio, retornan `not_implemented`. El flujo real funcionando es
legacy: `core/services/cotizacion_service.py`. **No existe un bounded
context de Cotizaciones funcional al que `CreateQuoteFromOpportunityUseCase`
pueda llamar hoy.** Construirlo habría significado o bien levantar un
bounded context de Cotizaciones completo (fuera de alcance de esta fase) o
bien puentear a `CotizacionService.crear()`, que además espera un
`cliente_id` legacy — el mismo gap de identidad. Diferido, documentado, no
fabricado con un puente frágil.

### Pedidos/Delivery (§49)

- **`CustomerOrdersSummaryQuery`** (`pedidos_whatsapp`, read-only) y
  **`CustomerDeliverySummaryQuery`** (`delivery_orders`/
  `delivery_order_history`, read-only) — nuevos permisos
  `CLIENTES.pedidos.ver`/`CLIENTES.entregas.ver`.
- `delivery_order_history` no tiene una columna "incidente" dedicada — se
  reutiliza `reason` (solo poblada en transiciones de excepción) como señal
  de incidente, mismo criterio "reusar la señal más cercana en vez de
  inventar una paralela" que CRM-6 ya siguió para OVERDUE.
- Ambas consultas guardan `_table_exists()` antes de leer (mismo patrón que
  `CustomerHistoryQueryService`, CRM-12) — un entorno de prueba o un
  despliegue que no cargó el schema legacy de Pedidos/Delivery contribuye
  "nada", no un `OperationalError`. Esto no es solo higiene de pruebas: la
  suite de regresión completa lo exigió — `test_customer_360_application.py`
  (CRM-12) usa una conexión que no incluye estas tablas legacy, y
  `Customer360QueryService._safe()` solo atrapa excepciones de dominio, no
  `sqlite3.OperationalError`.

### WhatsApp (§49) — parcialmente real, resto documentado como bloqueado

- **`CustomerWhatsAppSummaryQuery`** (nuevo permiso `CLIENTES.whatsapp.ver`):
  solo `has_active_whatsapp_consent` es real — reutiliza
  `CustomerConsentQueryService.is_active()` (CRM-9), que YA está indexado
  por el `customer_id` UUIDv7 propio de este bounded context, así que a
  diferencia de cada otra integración de esta fase, **no tiene el gap de
  identidad**.
- `last_conversation_at`/`open_conversations_count`/`handoff_pending`
  quedan siempre `None`/`0`/`False`, no omitidos del DTO. Investigación:
  el estado de conversación/handoff vive completo dentro de la base SQLite
  PROPIA del microservicio de WhatsApp (`whatsapp_service/state/
  conversation.py`, archivo `whatsapp_service/data/conversations.db`) — una
  base de datos físicamente distinta. Leerla directamente violaría la
  frontera de microservicio que CLAUDE.md §14 establece (WhatsApp se
  comunica vía REST/EventBus, no compartiendo tablas). Poblar esos tres
  campos de verdad necesita un cliente REST contra `whatsapp_service/erp/
  bridge.py` (auth, timeouts, comportamiento offline) o una proyección que
  WhatsApp mismo publique — ninguno existe hoy; una integración
  sustancialmente mayor que un query service, diferida.

### Fidelidad (§49)

- **`LoyaltyCustomerSummaryQuery`** (nombre literal de §57), nuevo permiso
  `CLIENTES.fidelidad.ver`: lee `loyalty_snapshots` (la fila resumen
  precomputada por Fidelidad — no `loyalty_ledger`/`tarjetas_fidelidad`,
  que el guardrail `test_customers_crm_does_not_own_loyalty.py` ya
  prohibía). `_table_exists()` guardado igual que Pedidos/Delivery.
- El campo del DTO originalmente llamado `points_balance` se renombró a
  `current_points` — el guardrail de Fidelidad hace un escaneo de
  substring de todo el árbol de código de este módulo, y `points_balance`
  es uno de los tokens prohibidos (nombre de una tabla/columna que
  Fidelidad posee), no solo un nombre de tabla — un recordatorio de que ese
  guardrail no distingue "referencio la tabla" de "coincido con el token
  por casualidad en un nombre de campo propio".

### Finanzas (§49) — extensión aditiva, no reconstrucción

`CustomerAccountsReceivableSummaryQuery`/`CustomerCreditQueryService` ya
existían completos desde CRM-8 (saldo/vencido/exposición). Solo faltaba el
cuarto campo que §49 nombra: **`receivable_status`** (`SIN_MOVIMIENTOS`/
`AL_CORRIENTE`/`VENCIDO`), derivado y nunca persistido — mismo criterio que
la fecha de vencimiento calculada en el mismo archivo. Campo aditivo en
ambos dataclasses; no rompe ningún consumidor existente (verificado: los
únicos dos sitios que construyen esos dataclasses son los propios archivos
que se modificaron).

### BI (§55)

**`CRMBIExportQueryService`** (`backend/application/crm/queries/
crm_bi_export_query_service.py`, nuevo permiso `CRM.bi.exportar`):
snapshot agregado de toda la compañía (sin eje de scope OWN/TEAM/BRANCH —
una exportación es inherentemente de compañía completa, §73 "exportar deja
evidencia"). Cuenta leads/conversión, oportunidades abiertas/ganadas/
perdidas, casos abiertos, incumplimientos de SLA (proxy simplificado, no
reimplementa el cálculo canónico de `SLAQueryService`), membresías de
segmento activas, incidencias de calidad abiertas — todo leyendo tablas que
el propio módulo Clientes/CRM ya posee (across sus 5 sub-contextos), nunca
alcanzando un módulo externo, así que a diferencia de cada otra integración
de esta fase, tampoco tiene el gap de identidad. BI mismo (cálculo de
CLV/churn/cohortes/forecast avanzado) queda fuera — ese es su propio
trabajo, no de esta fase.

### Composición en `Customer360QueryService`

Los cuatro resúmenes nuevos que sí tienen sentido en una vista de cliente
individual (`orders_summary`/`delivery_summary`/`whatsapp_summary`/
`loyalty_summary`) se agregaron aditivamente a `Customer360View`, cada uno
vía `_safe()` — igual que cada sección existente desde CRM-12. Los
eligibility queries y `CRMBIExportQueryService` NO se compusieron ahí
(elegibilidad es un chequeo de punto de venta que Ventas invoca
directamente, no una sección de expediente; BI export es de compañía
completa, no de un cliente).

## Decisiones documentadas (no adivinadas)

- **Los handlers de Ventas existen pero no están conectados a
  `core/events/wiring.py`.** El payload real de `VENTA_COMPLETADA` trae
  `cliente_id` legacy, que hoy NUNCA coincide con un `customers.id` UUIDv7
  — conectar la suscripción ahora sería código permanentemente muerto (cero
  matches posibles) en un archivo compartido fuera de los paquetes propios
  de este bounded context, que ninguna fase CRM anterior había tocado.
  Construir una heurística de emparejamiento por teléfono/RFC no fue
  pedido y sería frágil. Diferido a CRM-21/22 (o a quien reconcilie las
  identidades), documentado, no fabricado.
- **Todas las consultas de resumen de esta fase son código real y
  correcto, no simulacros** — dado un `customer_id` que sí coincidiera hoy
  (probado explícitamente en los tests de integración), aplican/leen
  correctamente. El hecho de que devuelvan vacío contra los datos reales de
  hoy es el mismo comportamiento correcto y documentado que
  `CustomerAccountsReceivableSummaryQuery` ya tiene desde CRM-8, ahora
  replicado con la misma disciplina en seis lugares más.
- **`CustomerCreditEligibilityQuery` no se construyó** — ya existía como
  `CheckCreditSaleEligibilityUseCase` (CRM-8). El permiso retroactivo que
  se había agregado antes de encontrarlo (`CREDIT_ELIGIBILITY_CHECK`) se
  removió — sin código muerto.
- **Cotizaciones queda completamente fuera de esta fase** — no hay bounded
  context de Cotizaciones funcional al que integrarse; construir uno está
  fuera del alcance que el usuario invocó para CRM-13.

## Permisos (retroactivos, CRM-2 no los anticipó)

`CustomerPermissions`: `COMMERCIAL_ELIGIBILITY_CHECK`, `ORDERS_VIEW`,
`DELIVERY_VIEW`, `WHATSAPP_VIEW`, `LOYALTY_VIEW` (+5 nuevos, 82 total).
`CRMPermissions`: `BI_EXPORT_VIEW` (+1 nuevo, 82 total). Registrados 1:1
en `core/security/permission_catalog.py`. (`CREDIT_ELIGIBILITY_CHECK` fue
agregado y luego removido en la misma fase — ver hallazgo de
`CheckCreditSaleEligibilityUseCase` arriba — así que no cuenta como
adición neta.)

## Verificación

```bash
python -m pytest tests/unit/customers/ tests/unit/crm/ tests/unit/customer_credit/ \
  tests/unit/customer_privacy/ tests/unit/customer_service/ tests/integration/customers/ \
  tests/integration/crm/ tests/integration/customer_credit/ tests/integration/customer_privacy/ \
  tests/integration/customer_service/ tests/architecture/test_customers_crm_*.py -q
# 761 passed, 1 skipped
```

- 33 pruebas nuevas: 8 unitarias de dominio (`Customer.record_sale_activity`/
  `record_sale_cancelled`) + 25 de integración (`test_crm_13_integraciones.py`)
  cubriendo cada pieza nueva, incluyendo explícitamente el contrato del gap
  de identidad (`test_handle_sale_completed_noops_on_unmapped_legacy_id`) y
  el camino feliz cuando el `customer_id` sí coincide.
- Fixture nueva `full_crm_conn_with_ops` (`tests/integration/customers/
  conftest.py`) — `full_crm_conn` más las formas mínimas de
  `pedidos_whatsapp`/`delivery_orders`/`delivery_order_history`/
  `loyalty_snapshots`.
- Los 21 guardrails de CRM-1 se re-ejecutaron completos y siguen en verde
  (incluyendo `test_customers_crm_does_not_own_loyalty.py`, que detectó
  correctamente la colisión de nombre `points_balance` descrita arriba).
- Migración 192 verificada end-to-end vía `scripts/bootstrap_db.py` contra
  una base nueva — idempotente en ambas direcciones (columnas ya presentes
  desde el `_DDL` actualizado, `_add_column` las detecta y no falla).
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **Reconciliación de identidad `clientes.id` ↔ `customers.id`** (y la
  tercera identidad INTEGER de `delivery_orders`) — CRM-21/22, como ya
  estaba anotado desde CRM-8. Es el bloqueador real detrás de casi todos
  los "diferidos" de esta fase.
- **Conectar `handle_sale_completed`/`handle_sale_cancelled` a
  `core/events/wiring.py`** — una vez resuelta la reconciliación anterior.
- **Cotizaciones/`CreateQuoteFromOpportunityUseCase`** — depende de que
  Cotizaciones tenga primero un bounded context de nueva arquitectura
  funcional; no es trabajo de CRM per se.
- **WhatsApp: última conversación/conversaciones abiertas/handoff** —
  necesita un cliente REST contra `whatsapp_service/erp/bridge.py` o una
  proyección publicada por WhatsApp; ninguno existe hoy.
- **`SALE_RETURNED`** — no existe el evento; si Ventas lo agrega en el
  futuro, el handler simétrico a `handle_sale_cancelled` es directo de
  añadir.
