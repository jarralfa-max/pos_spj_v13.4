# 03 — Inventario del esquema

Medido sobre una **copia** de `data/spj_pos_database.db`, con todas las migraciones aplicadas hasta la 347.

## Totales

| Objeto | Cantidad |
|---|---:|
| Tablas | 772 |
| Índices | 866 |
| Vistas | 7 (`v_negative_inventory`, `v_whatsapp_config`, `inventario`, `v_ventas_diarias`, `v_flujo_caja_diario`, `v_ventas_unificada`, `v_detalles_venta_unificada`) |
| Triggers | 13 (inmutabilidad de `inventory_movements`, `payments`, `sale_refunds`, `credit_notes`; protección de venta completada/cancelada; `trg_refund_no_excede`) |
| Tablas con FK | 373 (562 FK) |
| Filas totales | **3 503**; sólo 55 tablas con datos (`rol_permisos` 2 721, `schema_migrations` 325, catálogos semilla) |

**Lectura:** la instalación real todavía no tiene volumen operativo (1 usuario, 2 sucursales,
1 caja, 1 estación). Migrar datos a PostgreSQL es de bajo riesgo hoy. Migrar el esquema y la semántica no lo es.

## Identidad

| PK | Tablas |
|---|---:|
| `TEXT` simple (UUID) | 755 |
| Compuesta | 16 |
| Entera | **0** |
| Sin PK | 1 (`loss_investigation_evidence`) |

Mapeo a PostgreSQL: `TEXT` con UUIDv7 → `uuid`. Los ids los genera `backend/shared/ids.py::new_uuid` en
la aplicación; PG **no** genera ids de negocio.

## Tipos que cambian de semántica

### Dinero y cantidades en `REAL`

**203 columnas** con nombre de dinero o cantidad (precio, costo, monto, total, saldo, cantidad, peso…) son
`REAL`:

- **171 en tablas heredadas** (`ventas`, `detalles_venta`, `compras`, `inventario_actual`,
  `movimientos_inventario`, `lotes`, `cotizaciones`, `facturas_cfdi`…).
- **32 en tablas de aspecto canónico**, entre ellas:
  - `inventory_stock.quantity` (proyección de la migración 098, aún leída por BI y
    `inventory_application_service`);
  - `inventory_movements.*`, `inventory_reservations.reserved_qty`;
  - `sale_refunds.amount/quantity`;
  - `accounts_payable.amount/balance`, `accounts_receivable.amount/balance`;
  - `production_*`, `purchase_request*`, `treasury_capital.monto`.

El ledger canónico vigente (`inventory_ledger_lines`, `inventory_balances`, `sales`, `finance`) usa
**decimal en `TEXT`**, que es lo correcto y se mapea directo a `NUMERIC(p,s)`.

Regla para PostgreSQL:

- Sólo se replican tablas canónicas en `TEXT` decimal.
- Las 32 canónicas en `REAL` se migran primero a `TEXT` en SQLite (expandir → copiar → contraer) o se
  excluyen de la replicación si están muertas.

### Otros tipos

- **Fechas:** ISO en `TEXT`, con defaults `datetime('now')` (357 en migraciones). En PG se usa `timestamptz`
  y el instante lo fija la aplicación en UTC.
- **Booleanos:** `INTEGER 0/1` → `boolean`.
- **JSON:** textos `*_json` y `payload` → `jsonb` en el central.

## Duplicación de modelos

Conviven el modelo heredado y el canónico para los mismos hechos (ver memoria «Sales: two live
persistence models» y este inventario):

| Hecho | Heredado | Canónico |
|---|---|---|
| Venta | `ventas`, `detalles_venta`, `payments` (REAL) | `sales`, `sale_lines`, `sale_payments` |
| Inventario | `inventario_actual`, `movimientos_inventario`, `inventory_stock` | `inventory_ledger`, `inventory_ledger_lines`, `inventory_balances` |
| Lotes | `lotes`, `movimientos_lote` | `inventory_lots` |
| Clientes | `clientes` | `customers` (CRM-0) |

**Sólo el modelo canónico se replica al central.** Las tablas heredadas son candidatas a DEPRECAR con su
propio plan; no se portan a PostgreSQL.

## Migraciones

- `migrations/engine.py` registra **325** versiones; `migrations/standalone/` tiene **338** archivos.
- **No registrados (13):** `030_recipe_tables`, `032_meat_production`, `034_bi_tables`,
  `048_sync_improvements`, `066_erp_financial_model`, `076_recepciones_peso_total_kg`,
  `077_purchase_requests`, `093_delivery_schema_migrator`, `094_delivery_outbox`,
  `095_delivery_history_audit`, `172_inventory_ledger_line_unit_id`, `173_storage_location_type`,
  `200_uuid_identity_cutover`, más `_cutover_spec_generated` (spec, no migración). Varios son duplicados de
  número superados por su par registrado (030, 032, 034, 048). **No se borran** sin el análisis de 06 R-07.
- `CREATE TABLE` sin `IF NOT EXISTS`: 42 de 527 en migraciones, concentradas en 9 archivos (106, 292, 027,
  303, 298, 293, 108, 105, 092). Las muestreadas (106, 292) son reconstrucciones de tabla (`*__new`) o ramas
  condicionadas por la existencia previa. No se verificaron las 42 una por una.
- 19 migraciones contienen `DROP TABLE` (reconstrucciones). Ninguna se reutiliza en PostgreSQL: el central
  nace con su propio esquema base.

## Carril de esquema PostgreSQL (propuesta para 07)

El central **no** reproduce la historia de 338 migraciones SQLite. Nace de un esquema base PG por contexto
replicado (generado de `backend/infrastructure/db/schema/<ctx>_schema.py`, con tipos PG) y evoluciona con
migraciones PG propias. Se registra en el mismo `schema_migrations`, con un prefijo de carril. Alembic
no es necesario: el motor actual (lista explícita, `run(conn)`, idempotente) se extiende con un carril
`pg`. Se justifica en el ADR correspondiente.
