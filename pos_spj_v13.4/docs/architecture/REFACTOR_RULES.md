# Refactor Rules

## Control phrase

```text
No parchar.
No duplicar.
No ocultar legacy.
Proteger, extraer, probar, eliminar.
```

## Mandatory workflow

For each phase or module:

1. Read `docs/skills/SPJ_REFACTOR_SKILL.md` completely.
2. Read the relevant architecture documents in `docs/architecture/`.
3. Identify affected files.
4. Add or update protection tests before touching critical business logic.
5. Extract reads to QueryServices.
6. Extract mutations to Use Cases or Application Services.
7. Preserve functional business logic.
8. Remove legacy code only after the new route is tested and validated.
9. Run tests.
10. Report files changed, tests, risks, regressions, and recommended next step.

## Strict prohibitions

Do not:

- rewrite a full module blindly.
- change business rules without protection tests.
- create or alter schema from UI or services.
- add direct SQL in PyQt.
- pass the full `AppContainer` to new services.
- add arbitrary numeric defaults in UI.
- use long lists for entity selection.
- add plain phone `QLineEdit` capture.
- add loose relative paths.
- keep dead code only because it may be useful later.

## Acceptance direction

A refactored module is not complete until it satisfies the checklist in `docs/skills/SPJ_REFACTOR_SKILL.md`, including unit tests, integration tests, architecture tests, manual validation, event emission with `operation_id`, and legacy removal when safe.
