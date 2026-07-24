# Transfers schema consolidation — completada

`stock_transfers` y `stock_transfer_lines` son las únicas tablas del documento y
sus líneas. Embarques, recepciones, diferencias, devoluciones y custodia son
hechos hijos, no cabeceras paralelas. Inventario registra movimientos/balances y
reservas, pero no mantiene `inventory_transfer`.

El DDL canónico vive en `backend/infrastructure/db/schema/transfers_schema.py`,
ejecutado por la migración 154. Todos los IDs funcionales son UUIDv7 `TEXT` y
cantidades/pesos se guardan como strings decimales; no existe `REAL` crítico.

| Esquema eliminado | Sustitución | Consumidores |
|---|---|---:|
| `transferencias` | `stock_transfers` | 0 |
| `transferencia_detalle` | `stock_transfer_lines` | 0 |
| `transfers` | `stock_transfers` | 0 |
| `transfer_items` | `stock_transfer_lines` | 0 |
| `inventory_transfer` | `stock_transfers` + Inventory ledger | 0 |
| `inventory_transfer_line` | `stock_transfer_lines` + ledger lines | 0 |
