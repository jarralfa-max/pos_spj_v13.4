---
description: "SDLC etapa 3 — Build: plan aprobado primero, luego código incremental con pruebas (uso: /sdlc-build SDLC-CASH-003)"
argument-hint: "<ID>"
---

Etapa **Build** para `$ARGUMENTS`. Tiene dos pasos y entre ellos hay una aprobación mía.

## Prerrequisitos (detente si fallan)

- `pos_spj_v13.4/docs/sdlc/items/$ARGUMENTS/spec.md` existe y está **aprobado**.
- `git status` limpio. Si hay cambios que no son tuyos, avísame y para.

## Paso 1 — Plan (sin tocar código)

Si `plan.md` no existe o no está aprobado:

1. Crea la rama `sdlc/<id en minúsculas>` desde la rama base indicada en `docs/sdlc/README.md`.
2. Ejecuta la **línea base**: las pruebas de los módulos afectados más `python -m pytest tests/architecture -q`. Anota el resultado real, incluidos fallos que ya existían.
3. Escribe `docs/sdlc/items/$ARGUMENTS/plan.md` desde la plantilla: pasos pequeños, cada uno con archivo, cambio y cómo se verifica. El primer paso en ítems T0/T1 es la prueba de regresión que fija el comportamiento actual. Lista los archivos que no se tocan (shims intencionales de `CLAUDE.md`, legacy fuera de alcance).
4. Etapa en `BACKLOG.md` → `plan-borrador`. Commit `sdlc(build-plan): $ARGUMENTS`.
5. **Detente** y muéstrame el plan. No escribas código hasta que diga que está aprobado.

## Paso 2 — Implementación (solo con plan aprobado)

1. Marca el plan como aprobado (fecha) y la etapa como `en-build`.
2. Sigue el plan paso a paso. En cada paso: cambio mínimo → ejecutar su verificación → commit `fix|feat|refactor(<área>): … [$ARGUMENTS]`.
3. Reglas: UUIDv7 vía `backend/shared/ids.py`; rutas nuevas dentro de `pos_spj_v13.4/`; sin SQL en UI; operaciones de dinero con asiento balanceado; migraciones registradas en el motor oficial y en `migrations/MIGRATION_LOG.md`, probadas sobre una copia de la base en el scratchpad, nunca sobre un `.db` real.
4. Si descubres que el plan está mal o falta algo del spec, **no improvises en silencio**: detente, actualiza `plan.md` con la desviación y pídeme aprobación.
5. Si encuentras otro defecto fuera de alcance, no lo arregles aquí: agrégalo a `BACKLOG.md` como `intent-borrador`.

## Al terminar

Lista de commits, archivos tocados y resultado de la última ejecución de pruebas. Etapa → `en-test`. Siguiente paso: `/sdlc-test $ARGUMENTS` (idealmente en una sesión nueva).
