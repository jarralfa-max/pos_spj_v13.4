# LOSS-19 — Notifications and WhatsApp

- Deterministic policies map Losses events to severity, recipient roles and channels.
- Recipients are resolved by branch, role, active subscription and channel preferences.
- In-app and WhatsApp deliveries share one UUIDv7 delivery identity and provider idempotency key.
- Every attempt is audited as sent or failed; missing WhatsApp configuration fails explicitly.
- Source event, recipient and channel form the delivery uniqueness boundary.
- Routing operations are replay-safe through `loss_processed_operations`.
