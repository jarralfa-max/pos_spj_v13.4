# TRF-22 — Reporte de eliminación legacy

## Resultado

El corte se completó sin lectura dual, escritura dual, wrappers ni feature
flags. La entrada global carga `TransfersModuleHost`; este compone la vista con
el QueryRepository canónico de `stock_transfers`. Inventario conserva únicamente
ledger, balances, reservas y asignaciones; ya no conserva otro documento de
transferencia.

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|---|---|---|---:|
| `modulos/transferencias.py` | `frontend/desktop/modules/transfers/transfers_view.py` | DELETE | 0 |
| `TransferRepository` monolítico | UseCases + puertos enfocados | DELETE | 0 |
| `transferencias` | `stock_transfers` | DELETE | 0 |
| `transferencia_detalle` | `stock_transfer_lines` | DELETE | 0 |
| `transfers` | `stock_transfers` | DELETE | 0 |
| `transfer_items` | `stock_transfer_lines` | DELETE | 0 |
| `inventory_transfer` | ledger + `stock_transfers` | DELETE | 0 |
| `TRASPASO_INICIADO` | `TRANSFER_DISPATCHED` | DELETE | 0 |
| `TRASPASO_CONFIRMADO` | `TRANSFER_RECEIVED` | DELETE | 0 |
| `TRANSFER_ITEMS_PROCESS` | Inventory UseCases | DELETE | 0 |
| fallback `InventoryEngine` | `CanonicalInventoryTransferGateway` | DELETE | 0 |
| sugerencias legacy | `TransferSuggestionService` | DELETE | 0 |
| permiso general | permisos `TRANSFERS_*` | DELETE | 0 |
| QSS/tabs/UI legacy | Design System + sidebar canónico | DELETE | 0 |

## Evidencia de corte

1. Registro dinámico y `MainWindow` apuntan al host canónico.
2. Las migraciones base/023 y el esquema de Inventario ya no crean documentos
   de transferencia paralelos.
3. Se retiraron migraciones 031, 038 y 125 que recreaban las rutas eliminadas.
4. Se retiraron repositorio, QueryService, StatsRepository, suggestion engine,
   use cases y comandos legacy.
5. Se retiró el handler intermedio `TRANSFER_ITEMS_PROCESS`; los UseCases de
   Transferencias consumen exclusivamente los puertos canónicos de Inventario.
6. La allowlist final es `()` y los guardrails verifican imports, eventos y DDL.

## Allowlist

- Inicial: cuatro rutas UI/eventos registradas en allowlists generales, además
  de consumidores de caracterización legacy.
- Final: cero excepciones en `tests/architecture/transfers_legacy_allowlist.py`.

## Riesgos pendientes

No quedan riesgos de convivencia legacy dentro del bounded context. Las
integraciones concretas de infraestructura deben seguir respetando los puertos y
la atomicidad definidos en TRF-17; cualquier reintroducción queda bloqueada por
tests de arquitectura.
