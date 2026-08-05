# LOSS-17 — Corrective actions

Canonical lifecycle: `OPEN / IN_PROGRESS -> PENDING_VERIFICATION -> EFFECTIVE | INEFFECTIVE`.

- Creation is linked to a concluded investigation and assigns one UUIDv7 owner.
- Due dates must be future timezone-aware instants.
- Only the owner may submit execution evidence with a SHA-256 checksum.
- Verification requires an independent actor and records the effectiveness decision.
- Every transition is idempotent and emits an event through the transactional outbox.
