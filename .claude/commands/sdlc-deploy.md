---
description: "SDLC etapa 5 — Deploy: prepara PR y notas de liberación; el humano aprueba (uso: /sdlc-deploy SDLC-CASH-003)"
argument-hint: "<ID>"
---

Etapa **Deploy** para `$ARGUMENTS`. Preparas todo; **yo** hago el merge y, si aplica, disparo el release. Tú no haces merge, no creas tags `v*`, no publicas releases ni ejecutas el workflow `windows-release.yml`.

## Prerrequisitos (detente si fallan)

- Etapa `listo-deploy` y `test-report.md` sin fallos nuevos.
- `git diff <rama base>...HEAD --stat` no incluye `.db`, `.sqlite`, logs, `.env`, llaves ni binarios inesperados.

## Trabajo

1. Escribe `docs/sdlc/items/$ARGUMENTS/release.md` desde la plantilla: qué cambia para el usuario, checklist pre-merge marcado con evidencia, plan de reversa y verificación posterior.
2. Determina si el cambio afecta instalador/actualizador (`installer/`, `scripts/release/`, `backend/infrastructure/updater/`, `backend/application/software_updates/`): si sí, indica que hace falta una corrida de `windows-release.yml` y la política de compatibilidad para terminales que actualicen tarde u offline.
3. Si hubo migraciones: confirma que son aditivas o que tienen respaldo + reversa probados, y que el motor oficial las registra.
4. Actualiza `CLAUDE.md` o la documentación del módulo si el cambio altera una regla o contrato.
5. Commit `sdlc(deploy): $ARGUMENTS`. Haz push de la rama `sdlc/<id>` **solo si te lo pido**, y prepara el texto del PR hacia la rama base (título, resumen, enlaces a intent/spec/plan/test-report/release, checklist).
6. Etapa → `listo-deploy` hasta que yo confirme el merge; entonces → `liberado` con fecha.

## Al terminar

Muéstrame el texto del PR y lo que debo verificar después del merge. Siguiente: `/sdlc-maintain` tras el despliegue o en la revisión semanal.
