# Database Compatibility

## Current and future targets

SPJ uses SQLite currently and must be prepared for PostgreSQL in the future. New code must avoid patterns that make the future migration harder.

## Schema ownership

Only `migrations/` may create or alter schema.

Forbidden outside `migrations/`:

- `CREATE TABLE`
- `ALTER TABLE`
- `DROP TABLE`
- ad-hoc schema repair from UI
- service-level schema bootstrap

## UI database restrictions

PyQt must not execute SQL and must not manage transactions. UI reads must go through QueryServices, and UI mutations must go through Use Cases or Application Services.

## Transaction rules

- Transactions belong to infrastructure or Unit of Work abstractions.
- PyQt must not call `commit()` or `rollback()`.
- Use cases should coordinate transactional boundaries through injected dependencies.
- Critical mutations must be atomic and emit events only after successful persistence or according to a documented outbox strategy.

## SQL compatibility rules

New SQL must avoid SQLite-only behavior when a portable alternative exists.

Avoid new reliance on:

- SQLite-specific date functions when business logic can calculate dates in Python or use repository abstractions.
- `INSERT OR REPLACE` if it changes semantics compared with PostgreSQL upsert behavior.
- implicit boolean coercions that differ across databases.
- schema mutation on application startup.

## Repository boundary

Repositories own persistence details. Application services and use cases should depend on repository interfaces or explicit infrastructure abstractions, not UI database cursors.

## Paths and database location

Database paths and backups must be resolved through `AppPaths`, not loose relative paths. Desktop `.exe` deployments must store persistent data under an appropriate user data location, not beside temporary executable files.
