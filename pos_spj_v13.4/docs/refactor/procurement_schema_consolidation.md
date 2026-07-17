# PUR-13.8 — Consolidación del esquema de Compras

Auditoría de tablas legacy de Compras y decisión por tabla
(**REUSE · ALTER · REPLACE · MERGE · DROP**). El esquema canónico born-clean vive
en `backend/infrastructure/db/schema/procurement_schema.py` (migración 120, 23
tablas UUIDv7, dinero/cantidad en TEXT decimal, FKs, UNIQUE, CHECK, índices,
`version`, `created_at`, `updated_at`).

## Tablas legacy y decisión

| Tabla legacy | Origen | Reemplazo canónico | Decisión | Motivo / lectores vivos |
|---|---|---|---|---|
| `compras` | `m000_base_schema` | `direct_purchases` (+ líneas) | **REPLACE** | Aún leída por servicios legacy (inventory/sales/QR). No se dropea hasta migrar lectores. |
| `compras_detalle` | (no creada en migraciones activas) | `direct_purchase_lines` | **DROP** (cuando exista) | Sin definición activa; born-clean la sustituye. |
| `ordenes_compra` | `050_wa_integration`, base | `purchase_orders` (+ líneas + versiones) | **REPLACE** | Lectores WhatsApp/planeación. Migrar en 13.9. |
| `orden_compra_detalle` | base | `purchase_order_lines` | **REPLACE** | Junto con `ordenes_compra`. |
| `recepciones` | `031_inventory_engine` | `goods_receipts` (+ líneas + discrepancias) | **MERGE** | Recepción QR + inventario la usan; unificar a `GoodsReceipt` (13.13). |
| `recepciones_detalle` | inventario | `goods_receipt_lines` | **MERGE** | Con `recepciones`. |
| `facturas_proveedor` | (no creada) | `supplier_invoices` (+ matches) | **DROP** (cuando exista) | Born-clean la sustituye. |
| `pagos_compras` | (no creada) | evento `SUPPLIER_PAYMENT_SCHEDULED` → Tesorería | **DROP** (cuando exista) | Compras no guarda pagos; los agenda por evento. |
| `compras_directas` | (no creada) | `direct_purchases` | **DROP** (cuando exista) | Nombre alterno; born-clean canoniza. |
| `purchase_requests` | `077_purchase_requests` | `purchase_requisitions` (+ líneas) | **REPLACE** | Migrar lectores a solicitudes canónicas. |

## Reglas de la estructura final (no negociables)

La estructura final NO puede mantener: dos tablas de órdenes, dos de recepción,
dos de factura, columnas ambiguas, claves por texto libre, estados libres,
dinero/cantidad en `float`/`REAL`, ni relaciones sin foreign key.

El esquema canónico ya cumple:

- **UUIDv7** en todo `id` (`TEXT PRIMARY KEY`).
- **Decimal-compatible storage**: dinero/cantidad como cadenas decimales (TEXT),
  sin `REAL`.
- **Foreign keys** entre agregados y líneas.
- **Unique constraints**: `UNIQUE(operation_id)`, `UNIQUE(document_number)`,
  `UNIQUE(supplier_id, invoice_number)` (idempotencia estructural).
- **Check constraints** de estado (p. ej. `direct_purchases.status`,
  `goods_receipts.status`).
- **Version columns** (`purchase_orders.version` + `purchase_order_versions`).
- **`created_at` / `updated_at`** e índices por estado/proveedor/documento.

## Política de migraciones durante desarrollo (PUR-13.9)

Sin datos productivos que rescatar:

- no se crean migraciones de rescate innecesarias;
- no se conservan tablas obsoletas por compatibilidad ficticia;
- no se crean vistas para esconder duplicados;
- no se mantienen dos esquemas activos indefinidamente.

**Secuencia segura para consolidar** (cuando los lectores legacy de
`compras`/`ordenes_compra`/`recepciones`/`purchase_requests` migren a los
servicios canónicos): consolidar la migración canónica → actualizar bootstrap →
reconstruir la base de desarrollo → seeds → tests → eliminar migraciones rotas o
duplicadas según policy del repo. Todas las migraciones deben ser ordenadas,
idempotentes cuando el estándar lo exija, deterministas y compatibles con
bootstrap limpio.

## Estado actual

- **Sin colisión de nombres**: los nombres canónicos no chocan con las tablas
  legacy en español; ambas coexisten SOLO durante la transición controlada.
- El **DROP** de `compras`/`ordenes_compra`/`recepciones`/`purchase_requests`
  está **BLOCKED** hasta migrar sus lectores vivos (finance/treasury/QR/WhatsApp/
  planeación). Condición de eliminación registrada en la allowlist y en el
  reporte de eliminación.
