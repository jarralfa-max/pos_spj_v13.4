---
description: "SDLC autopiloto: design → plan → build → test → deploy de una ola completa sin detenerse; el humano revisa un solo PR al final (uso: /sdlc-auto ola 1 SDLC-ARQ)"
argument-hint: "<ola N [prefijo] | lista de IDs> [pr=ola|item]"
---

Modo **autopiloto** para `$ARGUMENTS`. Recorres las cinco etapas de cada ítem del lote **sin pedir aprobación entre etapas**. El único punto de control humano es el PR final. Aun así, cada etapa deja su artefacto (`spec.md`, `plan.md`, `test-report.md`, `release.md`) para que el humano pueda revisar cualquier decisión en el PR.

Aplica a cada ítem las reglas técnicas de `/sdlc-design`, `/sdlc-build`, `/sdlc-test` y `/sdlc-deploy` (léelas en `.claude/commands/`) y las de `CLAUDE.md`. Lo único que cambia es quién aprueba: tú avanzas solo, y te detienes **únicamente** por las causas de la sección 4.

## 1. Seleccionar el lote

1. Lee `pos_spj_v13.4/docs/sdlc/BACKLOG.md` y `README.md`. Calcula las olas con "Depende de" (igual que `/sdlc-lote`).
2. Selector: `ola N` (opcionalmente con prefijo, que arrastra sus dependencias externas de esa ola) o una lista de IDs.
3. Elegibles: etapa `intent-aprobado`, sin preguntas abiertas propias en el backlog, y todas sus dependencias en `liberado`.
4. Muestra elegibles y excluidos con su motivo. Si no hay elegibles, explica qué falta y detente.
5. `git status` limpio y rama base del README. Crea la rama de integración `sdlc/ola-<N>-<prefijo en minúsculas>` (o `sdlc/lote-<fecha>` para una lista de IDs) desde la rama base.

## 2. Ejecutar cada ítem (máximo 4 en paralelo)

Lanza un subagente por ítem, en un **worktree aislado**, con su rama `sdlc/<id>` creada desde la rama base. El subagente hace, en orden y sin detenerse:

1. **Design:** escribe `spec.md`. Toda decisión que el spec necesite debe resolverse con las "Decisiones aprobadas" del backlog o con `requisitos-arquitectura.md` y `CLAUDE.md`. Si queda una decisión de negocio que esas fuentes no contestan, **no la inventes**: marca el ítem `BLOQUEADO` con la pregunta y termina.
2. **Plan:** línea base real de pruebas y `plan.md`. En T0 y T1, el primer paso es una prueba de regresión que fija o reproduce el comportamiento.
3. **Build:** un commit por paso del plan. Migraciones probadas solo sobre copias de la base en un directorio temporal. Si el plan resulta incorrecto, corrígelo en `plan.md` explicando la desviación y continúa, salvo que la corrección toque archivos fuera de lo previsto para este ítem (causa de bloqueo).
4. **Test:** pruebas del ítem, `tests/architecture` y los segmentos afectados; compara contra la línea base. Fallos nuevos: corrígelos (máximo 2 intentos), si no, `BLOQUEADO`. Escribe `test-report.md`.
5. Marca `spec.md` y `plan.md` con `- **Estado:** aprobado por autopiloto (<fecha>) — pendiente de revisión humana en el PR`.
6. Devuelve: estado (`LISTO` o `BLOQUEADO`), rama, commits, archivos tocados, resultado de pruebas y, si aplica, la causa del bloqueo.

Los subagentes no editan `BACKLOG.md` ni archivos de otros ítems, y no hacen push.

## 3. Revisión independiente e integración (tú, el orquestador)

1. Por cada ítem `LISTO`, lanza un subagente `sdlc-reviewer` nuevo con el ID, la ruta de su `spec.md` y su rango de commits. Hallazgos **bloqueantes**: lanza un subagente de corrección en el mismo worktree y vuelve a revisar (máximo 2 rondas); si persisten, el ítem queda `BLOQUEADO`. Registra hallazgos y resolución en su `test-report.md`.
2. Integra en la rama de la ola, en orden de prioridad: `git merge --no-ff sdlc/<id>`. Si hay conflicto, resuélvelo solo si es mecánico (imports, listas, registros de migraciones); si toca lógica, aborta ese merge y deja el ítem como `BLOQUEADO (conflicto con <otro ID>)`.
3. En la rama de la ola, ejecuta `python -m compileall -q .`, `python -m pytest tests/architecture -q` y los segmentos de unit e integration de las áreas tocadas. Compara contra la línea base del triage (`docs/sdlc/baseline/`). Si la integración rompe algo que ningún ítem rompía por separado, identifica la combinación responsable y sácala de la ola.
4. Escribe `release.md` de cada ítem integrado y un reporte de la ola en `docs/sdlc/olas/ola-<N>-<prefijo>.md` con: ítems integrados, bloqueados y por qué, migraciones, resultados de pruebas antes/después, hallazgos del revisor, riesgos y el **checklist de revisión humana** (abajo).
5. Actualiza `BACKLOG.md` una sola vez: integrados → `listo-deploy` con la rama de la ola; bloqueados → se quedan en su etapa, con la causa en "Preguntas abiertas". Agrega en "Decisiones aprobadas": `<fecha> · autopiloto ola <N> · <IDs> · pendiente de aprobación humana en PR`.
6. Commit de `docs/sdlc/` en la rama de la ola.
7. Prepara el texto del PR (rama de la ola → rama base): resumen por ítem con enlaces a sus artefactos, migraciones, pruebas y el checklist. Con `pr=item`, prepara en su lugar un PR por ítem y el orden de merge.

## 4. Las únicas causas para detenerse o bloquear un ítem

- Una decisión de negocio sin respuesta en el backlog ni en los documentos de autoridad.
- Fallos nuevos que no se resuelven en 2 intentos, o hallazgos bloqueantes del revisor que persisten tras 2 rondas.
- Un cambio que necesitaría tocar una base de datos real, secretos, el instalador firmado o la infraestructura de producción.
- Un conflicto de lógica con otro ítem de la ola.

Un ítem bloqueado no detiene a los demás.

## 5. Checklist de revisión humana (va en el PR)

- [ ] Leí el reporte de la ola y la lista de bloqueados.
- [ ] Revisé el `spec.md` de cada ítem T0 (caja, ventas, finanzas, inventario, sync, seguridad, instalador).
- [ ] Las migraciones son aditivas o tienen reversa probada.
- [ ] Pruebas sin fallos nuevos respecto a la línea base.
- [ ] Hallazgos del revisor resueltos.
- [ ] CI de GitHub en verde.

## Nunca

Push, merge a la rama base, tags, workflows de release, tocar `.db` reales, ni marcar algo como `liberado`. Eso lo hace el humano al aprobar el PR.
