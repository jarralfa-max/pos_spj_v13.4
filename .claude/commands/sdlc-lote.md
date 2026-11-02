---
description: "SDLC en lote: ejecuta una etapa para varios ítems a la vez, por olas de dependencias (uso: /sdlc-lote design ola 1 | /sdlc-lote plan SDLC-ARQ | /sdlc-lote build ola 2)"
argument-hint: "<design|plan|build|test|deploy> <ola N | prefijo SDLC-XXX | lista de IDs | todos>"
---

Ejecuta la etapa indicada para **varios ítems en paralelo**. Argumentos: `$ARGUMENTS`

Esta orden no reemplaza las etapas individuales: aplica a cada ítem exactamente las reglas de `/sdlc-design`, `/sdlc-build`, `/sdlc-test` o `/sdlc-deploy` (léelas en `.claude/commands/`). Lo que cambia es que coordinas el lote y los puntos de aprobación humana se resuelven **una vez por lote**, no una vez por ítem.

## 1. Seleccionar el lote

1. Lee `pos_spj_v13.4/docs/sdlc/BACKLOG.md` y `pos_spj_v13.4/docs/sdlc/README.md`.
2. Calcula las **olas** con la columna "Depende de": ola 1 = ítems sin dependencias; ola N = ítems cuyas dependencias están todas en olas menores. Una dependencia a un ítem inexistente es un error: repórtalo y excluye el ítem.
3. Aplica el selector:
   - `ola N`: ítems de esa ola. Si no se indica prefijo, usa todos los ítems del backlog.
   - `ola N SDLC-ARQ`: ola N restringida a ese prefijo **más las dependencias externas que ese prefijo necesita** (por ejemplo, los SDLC-SYNC de los que dependen los SDLC-ARQ).
   - `SDLC-XXX` (prefijo), lista de IDs separados por coma, o `todos`.
4. Filtra por **elegibilidad** según la etapa:

| Etapa | El ítem debe estar en | Sus dependencias deben estar en | Además |
|---|---|---|---|
| design | `intent-aprobado` | `spec-aprobado` o posterior | Sin preguntas abiertas propias sin responder en el backlog |
| plan | `spec-aprobado` | `liberado` (su código ya está en la rama base) | — |
| build | `plan-aprobado` | `liberado` | — |
| test | `en-test` | — | — |
| deploy | `listo-deploy` | — | — |

5. Muestra una tabla: **elegibles** (ID, prioridad, nivel, ola) y **excluidos** (ID y motivo exacto: falta aprobación, dependencia X en etapa Y, pregunta abierta Z). Si no hay elegibles, explica qué falta y detente.
6. Antes de lanzar trabajo, confirma `git status` limpio y que estás en la rama base del README.

## 2. Ejecutar en paralelo

Lanza **un subagente por ítem**, como máximo **4 a la vez**; cuando uno termina, lanza el siguiente. Cada subagente recibe: el ID, la etapa, la ruta de su carpeta `items/<ID>/` y la instrucción de seguir el comando de esa etapa **con estas restricciones**:

- **No edita `BACKLOG.md`** ni ningún archivo de otro ítem. Solo escribe en `items/<ID>/` y, en build, en el código de su propio plan.
- **No hace commit en design ni en plan** (lo haces tú al consolidar). En build y test sí hace commits, en su propia rama.
- Devuelve un resumen de máximo 10 líneas: qué produjo, decisiones que requieren aprobación, bloqueos.

Reglas por etapa:

- **design:** los subagentes solo escriben `spec.md` (documentación), así que trabajan en el mismo árbol, cada uno en su carpeta.
- **plan:** cada subagente trabaja en un **worktree aislado** (aislamiento `worktree`), crea su rama `sdlc/<id>` desde la rama base, corre su línea base y escribe `plan.md` en esa rama. Al terminar, copia ese `plan.md` también a la rama base para que yo lo revise y apruebe en un solo lugar.
- **build:** antes de lanzar, compara las listas de archivos de cada `plan.md`. Los ítems que **comparten archivos** no corren en paralelo: van en secuencia, en el orden de la ola y luego por prioridad. Cada subagente trabaja en su worktree y su rama `sdlc/<id>`; si descubre que el plan es incorrecto, se detiene y lo reporta (no improvisa).
- **test:** cada ítem en su worktree; el revisor independiente es un subagente `sdlc-reviewer` nuevo por ítem, sin el razonamiento del implementador.
- **deploy:** escribe `release.md` y el texto de PR de cada ítem; indica el **orden de merge** según las dependencias. No hagas push ni merge.

## 3. Consolidar

1. Actualiza `BACKLOG.md` una sola vez con la nueva etapa y la rama de cada ítem procesado.
2. Commit de `pos_spj_v13.4/docs/sdlc/` con `sdlc(lote-<etapa>): <selector> — N ítems`.
3. Entrega:
   - tabla ID → resultado → archivo a revisar;
   - todas las **decisiones que requieren aprobación**, agrupadas por ítem;
   - excluidos y por qué;
   - el siguiente comando a correr.
4. **Detente.** El humano revisa y aprueba el lote (puede usar `python aprobar.py --etapa spec|plan ...`) antes de la siguiente etapa.

## Nunca

- Aprobar specs o planes en nombre del humano.
- Saltar una dependencia porque "parece independiente".
- Construir en paralelo dos ítems que tocan los mismos archivos.
- Hacer push, merge, tags o disparar workflows.
