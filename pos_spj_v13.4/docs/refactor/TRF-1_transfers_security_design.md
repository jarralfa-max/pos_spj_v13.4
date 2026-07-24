# TRF-1 — Seguridad de Transferencias

## Seguridad introducida

The Transfers application layer now defines a backend-only authorization policy.
Every future Use Case must call `require()` with its granular `TRANSFERS_*`
permission and every source/destination branch, warehouse, or location that is
being acted on. The UI may hide actions but never substitutes this validation.

`TransferAuthorizationPolicy.authorize_exception()` validates a second actor's
permission and creates an immutable `TransferAuthorizationGrant`, containing the
requester, authorizer, permission, reason, operation, transfer/shipment/receipt
references, Decimal quantity/weight, device, UUIDv7 grant ID, and timestamp. An
injected audit sink persists the grant in the same UnitOfWork as the sensitive
operation when the Use Cases are introduced.

## Segregation and limits

`TransferSegregationOfDutiesPolicy` blocks self-approval of elevated requests,
self-receipt by dispatcher, solo resolution of critical differences, same-party
custody handovers, and self-authorized reversals. `TransferLimitPolicy` accepts
only configuration-provided Decimal thresholds—there are no hard-coded quantity,
weight, or value limits.

## Required use-case gates

| Action | Permission | Scope | Extra control |
|---|---|---|---|
| Create/submit | `TRANSFERS_REQUEST_*` | origin/destination | requester identity |
| Approve | `TRANSFERS_APPROVE` | both nodes | elevated requester ≠ approver |
| Reserve/allocate/pick | `TRANSFERS_RESERVE/ALLOCATE/PICK*` | origin | lot override grant |
| Dispatch | `TRANSFERS_DISPATCH` | origin | partial-dispatch grant when required |
| Receive | `TRANSFERS_RECEIVE*` | destination | dispatcher ≠ receiver; tolerance grant |
| Resolve difference | `TRANSFERS_DIFFERENCE_*` | affected node | critical reporter ≠ resolver |
| Return/reverse | `TRANSFERS_RETURN_*` / `TRANSFERS_REVERSE` | physical node | independent reversal authorizer |

## Deferred persistence wiring

No legacy permission catalog, route, or database schema was changed in TRF-1.
They remain subject to the zero-consumer cutover gate recorded in TRF-0. The
next workflow Use Cases must persist `TransferAuthorizationGrant` and complete
the audit record atomically with the protected business change.
