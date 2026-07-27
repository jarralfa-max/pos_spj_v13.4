# Installer and Updater Rules

## Goal

The desktop PyQt application must be installable as a Windows `.exe` and prepared for safe version updates.

## Persistent data

Persistent data must live in user data directories resolved through `AppPaths`. Do not rely on loose relative paths for databases, backups, logs, manifests, downloads, or generated files.

## SQLite backup before update

Before applying a version update, the updater must create an automatic SQLite backup. The backup process must be explicit, logged, and recoverable.

## Update flow

A safe update flow should include:

1. Detect current version.
2. Download or read update manifest.
3. Validate manifest and package integrity.
4. Create SQLite backup.
5. Apply update.
6. Validate startup or migration state.
7. Provide rollback or restore instructions when possible.

## Migration discipline

Installer and updater code must not apply ad-hoc schema changes outside the migration system. Schema changes must remain in `migrations/`.

## Future API compatibility

Updater and installer infrastructure must not duplicate business logic. Desktop and future API clients should continue to share backend use cases.
