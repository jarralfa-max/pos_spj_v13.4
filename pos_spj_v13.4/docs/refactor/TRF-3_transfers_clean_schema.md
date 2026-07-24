# TRF-3 — Esquema limpio de Transferencias

## Bootstrap canónico

Migration `154_transfers_bounded_context_schema` is registered in the migration
engine and calls the sole DDL entry point, `create_transfers_schema`. The prior
unregistered file with a conflicting `135` number was removed; migration 135 is
already owned by Inventory labels.

## Identity, decimals, constraints, and indexes

All transfer context entities use `TEXT PRIMARY KEY` UUIDv7 identities. Every
quantity, weight, tolerance, and reference value is stored as `TEXT` decimal;
no transfer DDL contains `REAL`, `AUTOINCREMENT`, `lastrowid`, or numeric PKs.

The schema adds protected status and shipment-status CHECK constraints, document
source de-duplication, unique operation IDs for commands/shipments/receipts,
outbox de-duplication by `(operation_id, event_name, aggregate_id)`, and foreign
keys across transfer, line, shipment, receipt, difference, audit, authorization,
and outbox facts. It indexes status/node work queues, document children,
differences, offline synchronization, audit facts, and pending outbox events.

## Outbox and bootstrap tests

TRF-3 tests bootstrap an in-memory clean schema through migration 154, run
`foreign_key_check`, validate DDL constraints/indexes, and verify idempotent
outbox and parent-reference enforcement.
