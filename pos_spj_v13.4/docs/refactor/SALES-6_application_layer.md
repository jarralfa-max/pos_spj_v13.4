# SALES-6 — Application Layer (POS-6 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-5_repositorios_uow.md`.

## Alcance ejecutado

Master prompt §67, fase POS-6: "Commands. Queries. UseCases. DTO. Authorization. Tests."
Investigué primero (agente de research) cómo otros bounded contexts maduros de este repositorio
(cash_register, customers) estructuran su capa de aplicación, antes de diseñar nada — el
hallazgo más importante determinó la forma de toda la fase.

## Decisión de diseño central: sin `Command` dataclasses

La investigación encontró **dos convenciones de "Command" en este repositorio, no una**:

1. La antigua: `backend/application/commands/base_command.py::BaseCommand` +
   `backend/application/commands/sales_commands.py::CreateSaleCommand`/`CancelSaleCommand`
   (esta última YA EXISTE, pertenece al adaptador legacy de `SalesApplicationService` que
   SALES-0 clasificó como `WRAP_TEMPORARILY`).
2. La nueva, activa: `execute()` toma kwargs explícitos directamente, sin objeto `Command`
   intermedio — `backend/application/cash_register/shift_use_cases.py`,
   `backend/application/customers/use_cases/lifecycle_use_cases.py`.

Evidencia de que la convención (1) esta en retiro activo, no es la vigente:
`tests/architecture/allowlists.py` marca explícitamente un archivo hermano
(`customer_commands.py`) como "aislado. Mover a backend/application/customers/commands
(CRM-3)". Esta fase sigue la convención (2) — el bullet "Commands" del master prompt queda
satisfecho por las firmas tipadas de `execute()`, no por una clase `Command` nueva. Es la
misma reconciliación que cada fase anterior ya hizo cuando la lista abstracta del prompt
diverge de la convención real y vigente de este repositorio (SALES-1: orden del panel;
SALES-3: `SaleTotals` embebido; SALES-5: sin `Protocol` port).

## Entregables

**`backend/application/sales/result.py`** — `SaleResult` (mirrors `CustomerResult`:
`success`/`message`/`operation_id`/`entity_id`/`error_code`/`data`), más
`fail_from_domain_error(exc, operation_id)` — una sola tabla de mapeo excepción→código en vez
de un `try/except` repetido por caso de uso (13 excepciones de dominio mapeadas: desde
`PERMISSION_DENIED` hasta `SEGREGATION_OF_DUTIES`).

**`backend/application/sales/dto.py`** — `SaleLineDTO`/`SaleDTO`, proyecciones planas
inmutables (mirrors `CashShiftRow`, no `CustomerProfile` que embebe la entidad) — construidas
vía `from_entity()`.

**`backend/application/sales/use_cases/`** (10 casos de uso, sin herencia forzada donde las
firmas no coinciden — mismo criterio que `OpenCashShiftUseCase` de cash_register no forma
parte de ninguna jerarquía de transición):
- `cart_use_cases.py` — `StartSaleUseCase` (idempotente por `operation_id`, mirrors
  `CreateCustomerUseCase`), `AddSaleLineUseCase`, `UpdateSaleLineQuantityUseCase`,
  `RemoveSaleLineUseCase`, `AssignCustomerToSaleUseCase`.
- `discount_use_cases.py` — `ApplySaleDiscountUseCase`: el único caso de uso de esta fase que
  ejercita de verdad el mecanismo de autorización en caliente de SALES-2
  (`SalesAuthorizationPolicy.authorize_exception`) — un descuento grande sin
  `authorizer_user_id` falla con `DISCOUNT_NOT_ALLOWED`; con un autorizador válido y distinto
  del solicitante, se aplica; con el mismo usuario como autorizador, falla con
  `SEGREGATION_OF_DUTIES`. Cierra el círculo completo SALES-2 (política) → SALES-3 (dominio) →
  SALES-6 (orquestación) por primera vez.
- `lifecycle_use_cases.py` — `SuspendSaleUseCase` (resuelve `current_suspended_count` vía el
  nuevo `SaleRepository.count_suspended()` antes de invocar `sale.suspend()` — un caso de uso
  no puede delegar esa cuenta a una política pura sin I/O), `ResumeSaleUseCase`,
  `CancelSaleUseCase`, `BeginSaleCheckoutUseCase`.

**`backend/application/sales/queries/sale_query_service.py`** — `SaleQueryService`
(`get`/`list_suspended`, mirrors `CashShiftQueryService`: permiso primero, SQL propio vía el
repositorio, retorna DTOs). `list_suspended` es la implementación directa de
`ListSuspendedSalesQuery` (§40 del master prompt).

**Adiciones a `SaleRepository`** (SALES-5, extendido en esta fase porque un consumidor real lo
necesitaba): `count_suspended(branch_id, workstation_id=None)`, `list_suspended(...)` — el
hueco que la propia investigación de SALES-5 ya había señalado ("`Sale.suspend()` necesita
`current_suspended_count`... requeriría un nuevo método de repositorio").

**Nueva excepción de dominio**: `SaleNotFoundError` (faltaba en `backend/domain/sales/exceptions.py`
desde SALES-3 — un caso de uso necesita distinguir "la venta no existe" de cualquier otro
estado inválido).

**Eventos reales, no solo declarados**: cada caso de uso encola un evento real a `sales_outbox`
(vía `SalesEvents`/`sale_event_payload()` de SALES-3, dentro de la misma transacción que la
mutación — atomicidad real, verificada por test). Esto es lo primero que hace que
`sales_outbox` (creada vacía en SALES-4) reciba filas de verdad.

**Tests** (25 nuevos, todos verdes; 171 en total en toda la suite SALES-0..6, sin regresiones):
`tests/unit/test_sales_use_cases.py` (19: alta idempotente, cada caso de uso en su camino
feliz, permiso denegado, venta inexistente, autorización en caliente completa —incluyendo
auto-autorización rechazada—, atomicidad del outbox ante permiso denegado) y
`tests/unit/test_sales_query_service.py` (6: DTO de venta existente/inexistente, permiso
denegado lanza excepción, filtrado real por sucursal sin fuga entre sucursales).

## Lo que esta fase NO hizo (honesto, no fabricado)

- **`record_sales_audit_entry` (SALES-2) sigue sin conectarse.** Necesita un `container`
  (no solo la `connection` que estos casos de uso reciben, mismo patrón que
  cash_register/customers) — enhebrar `container` además de `connection` en cada `execute()`
  es una decisión de forma de API que se deja explícitamente para cuando una fase futura
  conecte estos casos de uso a la UI real (que ya tiene `container` a mano). Documentado en el
  docstring de `use_cases/_base.py`, no oculto.
- **`CompleteSaleUseCase` no existe.** `begin_checkout()` es el límite honesto que esta fase
  puede sostener — completar una venta depende de confirmación de pago real (POS-13/14), que
  no existe todavía. Construir un "complete" que finge que el pago ya se resolvió habría sido
  fabricar funcionalidad, no orquestarla.
- **Ningún caso de uso real de la UI llama a estos nuevos casos de uso todavía.**
  `modulos/ventas.py`/`core/services/sales_service.py` siguen siendo la única ruta operativa
  (SALES-0, sin cambios). Esta fase deja la capa de aplicación lista, no la conecta.
- **`AssignCustomerToSaleUseCase` se gatea bajo `SalesPermissions.SALE_CREATE`** — ni el
  catálogo de SALES-2 ni la lista §61 del master prompt nombran un código dedicado para
  "asignar cliente". Se documentó la elección en vez de inventar un permiso nuevo fuera de
  alcance de esta fase (que es orquestación, no expansión del catálogo).
- **Sin dispatcher que lea `sales_outbox`** — igual que SALES-4/SALES-5, sigue sin existir
  (el único de referencia real, `InventoryOutboxDispatcher`, sigue siendo código muerto en
  producción). Esta fase deja filas reales en la tabla; nada las despacha todavía.

## Siguiente fase

El master prompt continúa con POS-7 (Catálogo: QueryService, Search, Categories, Product
cards, Tests) — confirmar con el usuario antes de asumir orden, como en cada fase anterior.
