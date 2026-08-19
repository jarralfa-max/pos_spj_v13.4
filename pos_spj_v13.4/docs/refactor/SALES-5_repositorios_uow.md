# SALES-5 — Repositorios y UoW (POS-5 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-4_esquema_limpio.md`.

## Alcance ejecutado

Master prompt §67, fase POS-5: "Ports. Implementaciones. UnitOfWork. Atomicidad. Tests."
Conecta el dominio puro de SALES-3 (`Sale`/`SaleLine`) con el esquema de SALES-4
(`sales`/`sale_lines`/`sales_outbox`) — el primer código que realmente lee/escribe estas
tablas. Investigué primero las convenciones reales del repositorio (agente de research) antes
de diseñar: existen DOS familias de repositorios en este código base — con puerto `Protocol`
explícito en `domain/` (transfers, crm, customers, finance...) y sin puerto, clases SQLite
concretas directas (inventory, cash_register). Como `sales_schema.py` (SALES-4) ya declara
explícitamente que sigue las convenciones de `inventory_schema.py`, esta fase sigue la MISMA
familia (sin `Protocol`) para consistencia dentro del propio bounded context.

## Entregables

**`backend/infrastructure/db/repositories/sales/base.py`** — mirrors
`backend/infrastructure/db/repositories/inventory/base.py` literalmente (mismos nombres/firmas):
`now_iso()`, `dec_str()`/`to_decimal()` (conversión Decimal↔TEXT, `dec_str` rechaza `float`
explícitamente), `enum_value()`, y `SalesRepositoryBase` (`_query`/`_query_one`/`_execute`/
`_scalar`, acceso dict vía `zip(columns, row)`).

**`backend/infrastructure/db/repositories/sales/sale_repository.py`** — `SaleRepository`:
- `save(sale)` — upsert del header (`INSERT ... ON CONFLICT(id) DO UPDATE SET ...`, mirrors
  `purchase_order_repository.py`), luego `DELETE FROM sale_lines WHERE sale_id=?` +
  re-`INSERT` de todas las líneas actuales (reemplazo total, no diff — más simple y correcto
  dado que `Sale.remove_line()` significa que la línea realmente desapareció, no que quedó en
  cero). `product_snapshot` se serializa a JSON determinístico (`sort_keys=True`, mismo patrón
  que `cash_register`'s `_json()`).
- `get(sale_id)` / `get_by_operation_id(operation_id)` — dos consultas separadas (header, luego
  líneas `ORDER BY created_at`), sin `JOIN`, reconstruyen `Sale`/`SaleLine`/`Quantity`/
  `SaleTotals` directamente vía sus constructores (no las factory methods `start()`/`create()`
  — igual que `PurchaseOrderRepository._hydrate` reconstruye sin pasar por el factory de
  dominio, apropiado para rehidratación desde BD).
- `operation_exists(operation_id)` — idempotencia (§39), mismo idioma que
  `CreateCustomerUseCase`/`TransferWriteRepository`.

**`backend/infrastructure/db/repositories/sales/outbox_repository.py`** — `SalesOutboxRepository`
(`enqueue`/`list_pending`/`get_by_event_id`/`mark_dispatched`), mirrors
`InventoryOutboxRepository` letra por letra. Sin dispatcher — ver "Lo que NO hizo" abajo.

**`backend/infrastructure/db/repositories/sales/unit_of_work.py`** — `SalesUnitOfWork`:
`__init__(connection, *, owns_transaction=True)`, expone `uow.sales`/`uow.outbox` como
atributos, `__enter__`/`__exit__` (rollback en excepción, commit en salida limpia si no se
completó ya). Se eligió mirrors la versión de `InventoryUnitOfWork` (con flag
`owns_transaction`) en vez de la más simple de `CashRegisterUnitOfWork` (sin flag) —
justificación: un checkout de POS real necesitará componer escrituras de Sales + Inventory +
Caja dentro de un mismo `SAVEPOINT` externo, exactamente el escenario que el propio docstring
de `InventoryUnitOfWork` nombra.

**Atomicidad — verificada con tests reales, no solo documentada**: una excepción a mitad de
transacción revierte tanto el header `sales` como sus `sale_lines` juntos; un
`operation_id` duplicado (violación real de `UNIQUE`, `sqlite3.IntegrityError`) revierte la
transacción completa sin dejar líneas huérfanas; con `owns_transaction=False` la UoW nunca
toca `commit()`/`rollback()` de la conexión compartida (verificado forzando un rollback externo
después de que la UoW "termina" y confirmando que la fila desaparece).

**Tests** (18 nuevos, todos verdes; 146 en total en toda la suite SALES-0..5, sin regresiones):
- `tests/unit/test_sales_repository.py` — round-trip vacío/con líneas, reemplazo total de
  líneas, upsert idempotente por `id`, `get` de venta inexistente retorna `None`, descuento/
  impuesto de línea sobreviven el round-trip, `dec_str` rechaza float, y la familia de
  idempotencia por `operation_id` (`operation_exists`, `get_by_operation_id`, constraint
  `UNIQUE` real).
- `tests/unit/test_sales_unit_of_work.py` — commit conjunto de venta+líneas, outbox en la misma
  transacción, rollback conjunto ante excepción, atomicidad ante `operation_id` duplicado, y las
  dos ramas del flag `owns_transaction`.
- `tests/architecture/test_sales_unit_of_work_boundary.py` — mirrors
  `test_cash_register_unit_of_work_boundary.py`: ningún repositorio (fuera de la UoW misma)
  llama `commit()`/`rollback()` ni contiene DDL, y la UoW expone los dos repositorios
  requeridos.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **Ningún caso de uso real llama a `SalesUnitOfWork`/`SaleRepository` todavía.**
  `modulos/ventas.py`/`core/services/sales_service.py` siguen siendo la única ruta operativa
  real (confirmado en SALES-0, sin cambios). Esta fase deja el repositorio listo, no lo conecta.
- **Sin `Protocol`/puerto explícito en `backend/domain/sales/`** — decisión documentada, no
  omisión: la familia de convención más específica para este bounded context (inventory, cuyo
  esquema `sales_schema.py` ya declara seguir) no usa puertos tampoco. Si una fase futura
  necesita testear contra un doble de prueba sin SQLite real, se puede añadir un `Protocol`
  entonces sin romper `SaleRepository` (ya cumpliría su forma).
- **Sin dispatcher para `sales_outbox`.** Igual que en SALES-4: el único dispatcher de
  referencia real y más completo de este repositorio, `InventoryOutboxDispatcher`, se confirmó
  (de nuevo, en esta fase) que es código muerto — no lo instancia ningún punto de arranque de
  la app. Construir uno para Sales ahora sería infraestructura decorativa sin nada real que
  despachar.
- **Sin bloqueo optimista real por `version`.** La columna `version` se persiste (incrementa en
  cada mutación de dominio) pero `save()` no la usa para detectar escrituras concurrentes en
  conflicto (`ON CONFLICT DO UPDATE` es "last write wins", no "solo si version coincide”). No
  se encontró precedente de bloqueo optimista real en otros UoW de este repositorio (Inventory/
  Cash/Procurement tampoco lo implementan) — no se fabricó uno nuevo sin ese precedente.
- **`SaleLine.apply_tax()` no tiene un método equivalente en `Sale`** (a diferencia de
  `apply_line_discount`) — gap real de SALES-3, descubierto al escribir el test de persistencia
  de impuesto de línea; documentado ahí, no corregido en esta fase (fuera de alcance de
  Repositorios/UoW).

## Siguiente fase

El master prompt continúa con POS-6 (Application Layer: Commands, Queries, UseCases, DTO,
Authorization, Tests) — el paso natural ahora que dominio, esquema y repositorio existen.
Confirmar con el usuario antes de asumir orden, como en cada fase anterior.
