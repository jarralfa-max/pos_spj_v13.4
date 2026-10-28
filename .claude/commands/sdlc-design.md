---
description: "SDLC etapa 2 — Design: convierte un intent aprobado en spec.md (uso: /sdlc-design SDLC-CASH-003)"
argument-hint: "<ID>"
---

Etapa **Design** para el ítem `$ARGUMENTS`. No modificas código en esta etapa.

## Prerrequisitos (verifica y detente si fallan)

- Existe `pos_spj_v13.4/docs/sdlc/items/$ARGUMENTS/intent.md` y su estado es **aprobado** (en el archivo o en `BACKLOG.md`). Si no, dime qué falta y para.
- Las preguntas abiertas del intent están respondidas o marcadas como no bloqueantes.

## Trabajo

1. Lee el intent, `CLAUDE.md`, `docs/skills/SPJ_REFACTOR_SKILL.md` y, si el ítem toca arquitectura, permisos, caja/turnos, sincronización, instalador o actualizador, `docs/sdlc/inputs/requisitos-arquitectura.md`.
2. Lee el código real involucrado. Antes de proponer cualquier servicio, tabla, repositorio, evento o caso de uso nuevo, busca el equivalente existente en `backend/` y `core/`; si propones reemplazar algo, justifícalo con evidencia.
3. Escribe `docs/sdlc/items/$ARGUMENTS/spec.md` desde `_templates/spec.md`:
   - Comportamiento esperado con casos borde (offline, reintento, concurrencia, permisos, multi-sucursal) cuando apliquen.
   - Diseño por capas y contratos concretos.
   - Migraciones con compatibilidad de datos y reversa.
   - Criterios de aceptación numerados y verificables con pruebas que comprueban efectos reales, no que una ventana abre.
   - Decisiones que necesitan mi aprobación, cada una con opciones y tu recomendación.
4. Si el nivel es **T0**, incluye también: qué pruebas de regresión fijan el comportamiento actual antes del cambio, y cómo se prueba la migración sobre una copia de la base.
5. Actualiza la etapa en `BACKLOG.md` a `spec-borrador`. Commit de `docs/sdlc/` con `sdlc(design): $ARGUMENTS`.

## Al terminar

Resume el diseño en 5–8 líneas y lista las decisiones pendientes. Detente: yo apruebo el spec antes de `/sdlc-build $ARGUMENTS`.
