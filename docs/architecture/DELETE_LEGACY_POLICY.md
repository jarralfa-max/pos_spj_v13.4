# Delete Legacy Policy

## Principle

Dead, duplicated, or useless legacy code should be removed during refactor, but only when removal is safe and protected.

## Required conditions before deletion

Legacy code may be deleted only when:

1. A new canonical route exists.
2. The new route has protection tests.
3. The manual user flow still works.
4. There are no imports of the legacy code.
5. There are no dynamic references to the legacy code.
6. Deletion does not break CI or the affected test segment.

## What not to do

Do not preserve code only “por si acaso”. Do not hide legacy code behind unused branches, duplicate routes, or fallback mutations.

## Deletion report

When legacy code is deleted, the final report must list:

- files deleted.
- imports removed.
- tests covering the replacement route.
- manual validation performed.
- risks or regressions detected.

## Current phase note

FASE 0 creates documentation only. No legacy code should be deleted in this phase.
