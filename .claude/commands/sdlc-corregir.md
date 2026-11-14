---
description: "Corrección directa con subagentes: arregla los intents de uno o varios lotes de docs/sdlc/LOTES.md sin specs ni planes (uso: /sdlc-corregir ronda 1 | /sdlc-corregir lote 7 | /sdlc-corregir lotes 1,3,7)"
argument-hint: "ronda N | lote N | lotes N,M,..."
---

Modo **corrección directa** para `$ARGUMENTS`. No hay specs, planes ni reportes por ítem: cada intent se verifica, se reproduce con una prueba, se arregla y se commitea. Tú eres el **orquestador**: preparas el trabajo, lanzas un subagente por lote y consolidas. No arreglas código tú mismo.

## 1. Preparar (orquestador)

1. Lee `pos_spj_v13.4/docs/sdlc/LOTES.md` y toma los lotes del argumento (`ronda N` = todos los lotes de esa ronda).
2. Lee `pos_spj_v13.4/docs/sdlc/BACKLOG.md`. Para cada ítem de esos lotes:
   - **Procesar:** etapa `intent-aprobado` o `spec-aprobado`.
   - **Saltar:** `intent-borrador` (no aprobado), `listo-deploy`, `liberado`, `descartado`.
   - **Esperar:** si alguna de sus dependencias no está en `liberado` y tampoco va antes en el mismo lote.
3. Muestra una tabla lote → ítems a procesar / saltados (con motivo). Si un lote queda vacío, no lo lances.
4. Verifica `git status` limpio (si no, detente y avisa). Anota la rama actual como **rama base**.
5. Por cada lote a lanzar, crea su worktree y su rama desde la rama base:
   ```
   git worktree add ../spj-wt/lote-<N> -b fix/lote-<N>
   ```
   Si la rama ya existe, usa `git worktree add ../spj-wt/lote-<N> fix/lote-<N>` y continúa desde su último commit.

## 2. Lanzar subagentes

Lanza **un subagente por lote**, máximo **4 a la vez**; cuando uno termine, lanza el siguiente. Pasa a cada uno este encargo, completando los datos:

> Eres el corrector del **lote <N> (<área>)**. Trabajas **solo** dentro de la carpeta `<ruta absoluta de ../spj-wt/lote-N>`, en la rama `fix/lote-<N>`. Usa siempre rutas absolutas dentro de esa carpeta y empieza cada comando de terminal con `cd "<ruta>" &&`. No toques la carpeta principal del repo, no edites `BACKLOG.md`, no hagas push ni merge.
>
> Reglas del proyecto: `CLAUDE.md`. Lee `pos_spj_v13.4/docs/skills/SPJ_REFACTOR_SKILL.md` solo si el arreglo toca identidades/IDs. Si el ítem tiene `spec.md` aprobado, úsalo como guía.
>
> Procesa estos ítems **en este orden**: <lista de IDs>. Por cada uno:
> 1. Lee `pos_spj_v13.4/docs/sdlc/items/<ID>/intent.md`, incluidas las respuestas del responsable en "Preguntas abiertas", y las "Decisiones aprobadas" del backlog que lo mencionen.
> 2. Verifica en la ruta:línea de la evidencia que el problema sigue. Si ya está resuelto, regístralo como **DESCARTADO** con la evidencia y sigue.
> 3. Escribe una prueba que reproduzca el problema y confirma que **falla**.
> 4. Haz el arreglo mínimo. Nada de refactorizar fuera del problema. UUIDv7 con `backend/shared/ids.py`, dinero con `Decimal`, sin SQL en la UI; migraciones registradas en el motor oficial y probadas solo sobre copias de la base en un directorio temporal.
> 5. Corre solo esa prueba y las del módulo tocado, desde `pos_spj_v13.4/`: `QT_QPA_PLATFORM=offscreen python -m pytest <rutas> -q -x -p no:cacheprovider`. Si una corrida pasa de 10 minutos, detenla y anota qué prueba se colgó.
> 6. Si no pasa en 3 intentos, deshaz los cambios de ese ítem con `git restore --source=HEAD --staged --worktree <archivos>`, regístralo como **BLOQUEADO** con la causa y sigue con el siguiente.
> 7. Si el arreglo necesita una decisión de negocio que no está respondida, no la inventes: **BLOQUEADO** con la pregunta, y sigue.
> 8. Si un ítem depende de otro de este lote que quedó BLOQUEADO, márcalo **ESPERA** y sigue.
> 9. Commit: `fix(<área>): <título corto> [<ID>]`.
>
> Al terminar el lote:
> - Desde `pos_spj_v13.4/`, una sola vez: `python -m compileall -q .` y `QT_QPA_PLATFORM=offscreen python -m pytest tests/architecture -q -p no:cacheprovider`, más `tests/unit` y `tests/integration` de las áreas tocadas. Corrige lo que este lote haya roto; distingue fallos que ya existían (compáralos contra `docs/sdlc/baseline/`).
> - Relee tu diff completo (`git diff <rama base>...HEAD`) buscando errores de dinero, turnos, permisos o datos.
> - Escribe `pos_spj_v13.4/docs/sdlc/lotes/lote-<N>.md`: por ítem, estado (LISTO / DESCARTADO / BLOQUEADO / ESPERA), qué se cambió, la prueba que lo cubre y la causa si no quedó; migraciones; resultados de las pruebas finales; fallos preexistentes. Haz commit de ese archivo.
> - Devuelve en máximo 15 líneas: ítems por estado, commits, archivos tocados, resultado de pruebas y bloqueos.

## 3. Consolidar (orquestador)

Cuando todos los subagentes terminen:

1. Por cada lote, cierra su worktree sin borrar la rama: `git worktree remove ../spj-wt/lote-<N>`. Si se niega porque quedaron cambios sin commit, no uses `--force`: repórtalo.
2. En la rama base, actualiza `BACKLOG.md` **una sola vez**: LISTO → `listo-deploy` con la rama `fix/lote-<N>`; DESCARTADO → `descartado`; BLOQUEADO y ESPERA no cambian de etapa, y su causa va a "Preguntas abiertas para el responsable". Commit `sdlc(corregir): <argumento>`.
3. Entrega:
   - tabla lote → listos / descartados / bloqueados / en espera;
   - todas las preguntas nuevas para el responsable;
   - por lote, el texto del PR (`fix/lote-<N>` → rama base) con la lista de ítems, pruebas, migraciones y un checklist: [ ] revisé el diff de caja/ventas/finanzas · [ ] migraciones aditivas o con reversa · [ ] sin fallos nuevos · [ ] CI en verde;
   - los comandos para subir cada rama: `git push -u origin fix/lote-<N>`.
4. **No** hagas push, merge ni borres ramas: eso lo hace el responsable.
