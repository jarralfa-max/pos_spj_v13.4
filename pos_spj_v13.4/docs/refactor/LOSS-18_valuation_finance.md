# LOSS-18 — Valuation and Finance

- Every line records a UUIDv7 cost reference, source type, quantity/weight basis and exact Decimal unit cost.
- Each valuation is an immutable snapshot with gross, approved recovery and net loss values.
- Approved `loss_recoveries` are the canonical recovery source; net loss is `gross - approved recovery`.
- Optimistic versioning prevents stale revaluation writes.
- `LOSS_VALUED` and `LOSS_FINANCE_RECOGNITION_REQUESTED` are emitted through the transactional outbox.
