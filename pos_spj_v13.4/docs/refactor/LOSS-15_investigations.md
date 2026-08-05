# LOSS-15 — Investigations

Canonical workflow: `OPEN -> IN_PROGRESS -> CONCLUDED`.

- Opening requires a scoped loss case, an assigned UUIDv7 user, a future UTC due date and a reason.
- Evidence is immutable, linked to its investigation phase and protected by a SHA-256 checksum.
- Findings are first-class UUIDv7 records; each includes a cause code, description and evidence.
- Conclusion requires at least one finding, conclusion evidence and a user other than the opener.
- Every mutation is idempotent and writes its domain event to the Losses outbox in the same transaction.
