# SPJ ERP/POS Architecture

## Purpose

This document defines the target architecture for the SPJ ERP/POS refactor. It is documentation only and does not change business logic.

The target is a maintainable, testable system where PyQt Desktop, a future FastAPI API, and any future web app share the same backend use cases and domain rules.

## Target layers

```text
frontend/desktop
  -> backend/application/use_cases
  -> backend/domain
  -> backend/infrastructure/db
  -> SQLite now / PostgreSQL future
```

## Layer responsibilities

### Frontend Desktop

- Presents Spanish user-facing text.
- Collects user input.
- Uses standard UI components for numbers, money, phones, addresses, and entity search.
- Calls QueryServices for reads.
- Calls Use Cases or Application Services for mutations.
- Does not execute SQL.
- Does not call `commit()` or `rollback()`.
- Does not create or alter schema.

### Backend Application

- Exposes use cases for critical operations.
- Coordinates transactions through explicit dependencies.
- Defines commands, DTOs, queries, and event handlers.
- Emits domain events for critical mutations with `operation_id`.
- Keeps names, classes, modules, and APIs in English.

### Domain

- Owns business rules and policies.
- Must not depend on PyQt, FastAPI, SQLite-specific SQL, or UI widgets.
- Preserves functional rules during refactor unless protected tests justify a change.

### Infrastructure

- Implements repositories, database access, hardware integrations, maps, printers, WhatsApp, and updater integrations.
- Supports SQLite now and PostgreSQL-compatible patterns for future migration.
- Does not leak database implementation details into UI.

### Shared

- Provides cross-cutting primitives such as events, errors, result objects, IDs, and `AppPaths`.
- Centralizes paths and environment-specific filesystem decisions.

## Canonical operation rule

Every critical business operation must have one canonical route.

Examples:

- Register waste -> `RegisterWasteUseCase`
- Create sale -> `CreateSaleUseCase`
- Dispatch transfer -> `DispatchTransferUseCase`
- Receive transfer -> `ReceiveTransferUseCase`
- Generate Z cut -> `GenerateZCutUseCase`
- Convert quote to sale -> `ConvertQuoteToSaleUseCase`

## Dependency direction

Dependencies must point inward:

```text
UI/API -> Application -> Domain
Application -> Infrastructure interfaces
Infrastructure -> concrete external systems
```

The UI must not know database schema details. Services must not receive a full application container; dependencies must be injected explicitly.

## Refactor sequencing

The refactor must proceed in small phases and modules. Each module requires protection tests before critical logic is changed, and legacy code can only be removed after the new canonical path is tested and manually validated.
