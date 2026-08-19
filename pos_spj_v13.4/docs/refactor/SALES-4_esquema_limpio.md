# SALES-4 — Esquema limpio (POS-4 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-3_dominio.md`.

## Alcance ejecutado

Master prompt §67, fase POS-4: "UUIDv7. Decimal. Constraints. Índices. Outbox. Tests." Crea la
persistencia born-clean para el agregado `Sale`/`SaleLine` que SALES-3 construyó en dominio
puro (sin schema todavía). Mirrors `backend/infrastructure/db/schema/inventory_schema.py`
exactamente — el bounded context más cercano en convención ya validada (sin SQLAlchemy, DDL
como tuplas de strings crudos, `TEXT PRIMARY KEY` para UUIDv7, `TEXT` para todo lo Decimal,
sin CHECK de enum en SQL).

## Entregables

**`backend/infrastructure/db/schema/sales_schema.py`** — 3 tablas nuevas (`SALES_TABLES`):
- `sales` — persistencia plana del aggregate root `Sale`. Los 8 componentes de `SaleTotals`
  (`gross_subtotal`, `discount_total`, `promotion_total`, `coupon_total`, `loyalty_total`,
  `tax_total`, `rounding_adjustment`, `total`) se guardan como columnas `TEXT` separadas — el
  repositorio (POS-5, no construido aún) las reensambla en un solo `SaleTotals` VO al leer. Esto
  no reintroduce la duplicación que SALES-3 evitó: la fila SQL y el VO de dominio son capas
  distintas, la regla "una sola evaluación de precios" es sobre lógica de cálculo, no sobre
  forma de almacenamiento. `operation_id TEXT NOT NULL UNIQUE` implementa la idempotencia de
  §39 directamente a nivel de constraint de base de datos.
- `sale_lines` — persistencia de `SaleLine`, incluye `product_snapshot TEXT` (JSON) para
  preservar nombre/sku/unidad al momento de agregar (§11), `quantity`/`quantity_unit` separados
  (reconstruye el VO `Quantity`), `FOREIGN KEY` implícita a `sales(id)`.
- `sales_outbox` — tabla de outbox transaccional (§39), mirrors `inventory_outbox` exactamente:
  `event_id TEXT NOT NULL UNIQUE`, `status` PENDING/DISPATCHED/DEAD_LETTER.

**Decisión de nombres documentada**: `sales`/`sale_lines` son nombres nuevos, sin colisión con
las tablas legacy `ventas`/`detalles_venta` (que siguen intactas, siguen siendo la única ruta de
escritura real hoy). `payments`/`sale_refunds` ya están tomados por `_create_ventas`
(`migrations/m000_base_schema.py`) — si una fase futura necesita una tabla de pagos para el
agregado nuevo, debe llamarse `sale_payments`, nunca `payments` (colisión real evitada, no
solo hipotética — confirmado por investigación antes de nombrar nada).

**Sin CHECK constraints de enum, a propósito**: igual que `inventory_schema.py`, los valores de
`status` se documentan en un comentario `-- DRAFT | ACTIVE | ...` pero no se validan con SQL
`CHECK` — la validez de transición vive exclusivamente en
`backend/domain/sales/policies/lifecycle_policies.py::SaleLifecyclePolicy`. Confirmado como
convención real de este repositorio (no una omisión), no solo asumido.

**Índices** (7): `idx_sales_branch_status`, `idx_sales_cashier`, `idx_sales_customer`,
`idx_sales_workstation_status` (soporta la futura consulta de ventas suspendidas por estación,
gap ya identificado en `SALES-0_auditoria.md`), `idx_sale_lines_sale_id`,
`idx_sale_lines_product_id`, `idx_sales_outbox_status`.

**Migración** `migrations/standalone/198_sales_bounded_context_schema.py` — siguiente número
libre confirmado (197 era el más alto registrado), `run(conn)`/`up = run`, llama
`create_sales_schema(conn)`. Registrada en `migrations/engine.py` (`_Migration("198", ...)`).
Verificado con una corrida completa de `scripts/bootstrap_db.py` contra una DB nueva: la
migración 198 se ejecuta sin error dentro de la cadena completa de 198 migraciones, y las 3
tablas quedan creadas con las columnas esperadas.

**Tests** (16 nuevos, todos verdes):
- `tests/unit/test_sales_schema.py` — tablas creadas, idempotencia de la creación, ninguna
  columna de dinero/cantidad es `REAL`, todo `id` es `TEXT PRIMARY KEY` sin `AUTOINCREMENT`,
  `drop_sales_schema` limpia las 3 tablas, `UNIQUE(operation_id)` y `UNIQUE(event_id)` rechazan
  duplicados reales (`sqlite3.IntegrityError`), la migración 198 existe y está registrada en
  `engine.py`.
- `tests/architecture/test_sales_domain_contract.py` — cierra un gap real que SALES-3 dejó
  abierto (no existía guardrail de arquitectura para el dominio nuevo, a diferencia de
  `test_cash_register_domain_contract.py`): sin imports de `sqlite3`/`PyQt`/`repositories`/
  `infrastructure.db` ni literales `float` en todo `backend/domain/sales/`, el catálogo de
  eventos cubre el ciclo de vida completo y nunca usa nombres legacy en español, `Sale`/
  `SaleLine` existen, `SaleLifecyclePolicy` es realmente usado por el agregado, y —hallazgo
  nuevo de esta fase— **ningún archivo fuera de `sale_totals_service.py`/`sale_totals.py`
  construye un `SaleTotals` directamente** (test AST/grep que lo verifica, no solo lo asume).

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No hay repositorio.** `sales`/`sale_lines`/`sales_outbox` existen como tablas vacías; nada
  las lee ni las escribe todavía — ningún código de aplicación construye un `Sale` desde una
  fila SQL ni lo persiste. Eso es POS-5 (Repositorios y UoW), el propio prompt lo separa.
- **El outbox no tiene dispatcher.** `sales_outbox` es solo la tabla — no existe un
  `SalesOutboxDispatcher` (el patrón más rico, `InventoryOutboxDispatcher`, existe para
  Inventario pero **no está conectado a ningún punto de arranque real de la app** — confirmado
  por búsqueda, solo lo ejercitan tests de integración). No se fabricó un dispatcher conectado
  para Sales tampoco; sería trabajo prematuro sin un caso de uso real que publique eventos
  primero.
- **Ninguna fila real se ha insertado nunca en estas tablas** fuera de los tests — la migración
  198 corre en cadena y las deja vacías, exactamente como se espera para un esquema recién
  nacido sin consumidores todavía.
- **No se tocaron las tablas legacy** `ventas`/`detalles_venta`/`payments`/`sale_refunds` — POS-4
  fue estrictamente aditivo.

## Siguiente fase

El master prompt continúa con POS-5 (Repositorios y UoW: Ports, Implementaciones, UnitOfWork,
Atomicidad, Tests) — el paso lógico inmediato dado que ahora existen tanto el dominio (SALES-3)
como el esquema (SALES-4) que un repositorio necesita conectar. Confirmar con el usuario antes
de asumir orden, como en cada fase anterior.
