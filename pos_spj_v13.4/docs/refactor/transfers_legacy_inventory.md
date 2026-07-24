# Transfer legacy inventory (TRF-0)

## Findings

| Legacy element | Classification | Canonical destination | Preserved rule |
|---|---|---|---|
| `modulos/transferencias.py` | REWRITE | `frontend/desktop/modules/transfers/` | dispatch, reception, QR entry point |
| `repositories/transferencias.py` | DELETE | transfer use cases plus focused repositories | atomic dispatch/receipt |
| `transfers` / `transfer_items` | DELETE | `stock_transfers` / `stock_transfer_lines` | duplicate reception and over-receipt guards |
| `transferencias` / `transferencia_detalle` | DELETE | `stock_transfers` / `stock_transfer_lines` | operation idempotency |
| `TRANSFER_ITEMS_PROCESS` | REWRITE | inventory gateway invoked by use case | post-commit inventory integration |
| `TRASPASO_*` | DELETE | `backend.domain.transfers.events.TransferEvents` | lifecycle notifications |
| `core/services/transfer_suggestion_engine.py` | REWRITE | `backend/domain/transfers/services/transfer_suggestion_service.py` | DOS, CV, demanda, redistribución |

## Evidence and constraints

The legacy UI constructs `TransferRepository`, uses `QTabWidget`, local widgets,
and legacy event names.  The repository conditionally invokes an event handler,
which is a prohibited direct inventory fallback.  Both legacy schema families
store critical quantities as SQLite `REAL`.  The new bounded context instead
uses UUIDv7 (`new_uuid`), decimal strings in the schema, a single `operation_id`,
and post-commit outbox records.

## Removal gate — completado en TRF-22

Imports, registro dinámico, ruta global, suscriptores y pruebas de
caracterización alcanzaron cero consumidores antes de eliminarse. DOS/CV y
Forecast viven en `TransferSuggestionService`; no queda engine legacy ni
allowlist temporal.
