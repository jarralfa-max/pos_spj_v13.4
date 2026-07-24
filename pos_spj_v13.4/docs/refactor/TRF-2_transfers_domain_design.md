# TRF-2 — Dominio de Transferencias

## Aggregate and lines

`StockTransfer` owns the logistics workflow; it does not write inventory. Each
`StockTransferLine` carries requested, approved, reserved, picked, dispatched,
received, accepted, and rejected Decimal quantity/weight facts, plus pieces and
the lot/quality/temperature requirements. A line can never approve, reserve,
pick, dispatch, or receive beyond its preceding lifecycle fact.

## Workflow

The domain protects request submission, partial/full approval, reservation,
picking, readiness, partial/full dispatch, cumulative receipt, difference
review, closure, rejection, and cancellation. Dispatch requires picked stock;
cancellation is rejected after physical dispatch. Receipt operations are
idempotent in the aggregate and each receipt contains unique transfer lines.

`TransferWorkflowPolicy` is the read-only, complete transition catalog for
application/UI queries; mutation remains protected by aggregate methods.

## Policies and events

TRF-1's segregation and configured Decimal limits remain domain policies.
Canonical `TransferEvents` now rejects unknown/legacy event names and requires
the distinct operation, entity, and user identifiers required by post-commit
outbox handlers. No `TRASPASO_*` event exists in the Transfers domain.

## Coverage

Domain tests cover cumulative catch-weight receipt, partial approval, picking
protection, over-receipt, duplicate receipt operation, valid/invalid workflow
transitions, and canonical event validation.
