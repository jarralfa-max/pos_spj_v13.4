# SDLC de SPJ ERP — ciclo de 6 etapas con Claude Code

Este directorio implementa el ciclo **Plan → Design → Build → Test → Deploy → Maintain** del *AI-Native SDLC Playbook* sobre el repositorio real de SPJ ERP. La idea central: en lugar de un prompt gigante que intenta arreglar todo de una vez, cada problema de la app se convierte en un **ítem** que recorre las seis etapas, y cada etapa deja un artefacto versionado en Git. Así cualquier cambio se puede rastrear, revisar y revertir.

## El ciclo

```
          ┌───────────────────────────────────────────────────────────┐
          ▼                                                           │
 /sdlc-plan ──► intent.md ──[aprobación humana]──► /sdlc-design ──► spec.md
                                                                     │
                                         [aprobación humana del spec]│
                                                                     ▼
 /sdlc-maintain ◄── release.md ◄── /sdlc-deploy ◄── /sdlc-test ◄── /sdlc-build
   (nuevos intents al BACKLOG)  [gate humano:   test-report.md   plan.md ─[aprobación]─► código
                                 merge/release]  + revisión
                                                 independiente
```

| Etapa | Comando | Artefacto | Gate humano |
|---|---|---|---|
| 1. Plan | `/sdlc-plan triage` o `/sdlc-plan <problema>` | `BACKLOG.md`, `items/<ID>/intent.md` | Apruebas el intent |
| 2. Design | `/sdlc-design <ID>` | `items/<ID>/spec.md` | Apruebas el spec |
| 3. Build | `/sdlc-build <ID>` | `items/<ID>/plan.md` + código + commits | Apruebas el plan antes de tocar código |
| 4. Test | `/sdlc-test <ID>` | `items/<ID>/test-report.md` | Revisas el reporte y la revisión independiente |
| 5. Deploy | `/sdlc-deploy <ID>` | `items/<ID>/release.md` + PR preparado | **Tú** haces el merge / disparas el release |
| 6. Maintain | `/sdlc-maintain [área]` | Nuevos intents en `BACKLOG.md` | Priorizas el backlog |

## Cómo arreglar "todo lo que está mal" sin un solo prompt

1. **Una vez:** `/sdlc-plan triage`. Barre toda la app por bounded context, corre los segmentos de CI, lee las auditorías existentes y llena `BACKLOG.md` con ítems priorizados (cada uno con su `intent.md` borrador).
2. **Por cada ítem, en orden de prioridad:** `/sdlc-design ID` → `/sdlc-build ID` → `/sdlc-test ID` → `/sdlc-deploy ID`. Una sesión nueva de Claude Code (o `/clear`) por etapa mantiene el contexto limpio; el estado vive en los archivos, no en el chat.
3. **Después de cada release o cada semana:** `/sdlc-maintain`. Revisa logs, scripts de integridad y pruebas; lo que encuentre entra como nuevos intents. El ciclo se cierra solo.

Puedes tener varios ítems en vuelo a la vez si no tocan los mismos archivos; para eso usa worktrees (`claude --worktree` o una carpeta por rama).

## Identificadores y carpetas

- ID: `SDLC-<AREA>-<NNN>`, por ejemplo `SDLC-CASH-003`, `SDLC-FIN-001`. `AREA` usa los prefijos de flujo de trabajo que ya existen en `docs/refactor/` (CASH, SALES, FIN, CRM, LOY, PROC, ORD, TRF, ASSET, BI, LOSS, WA, SET…) o `CORE`, `SYNC`, `SEC`, `INST` para temas transversales.
- Artefactos: `docs/sdlc/items/<ID>/{intent,spec,plan,test-report,release}.md`. Plantillas en `docs/sdlc/_templates/`.
- Entradas de diseño de referencia: `docs/sdlc/inputs/` (por ejemplo `requisitos-arquitectura.md`).

## Ramas

- **Rama base:** `claude/erp-financial-bounded-context-uqxz6b` (cámbiala aquí cuando cambie).
- Cada ítem trabaja en `sdlc/<ID-en-minúsculas>` creada desde la rama base y vuelve a ella por PR.
- Nadie hace push a `main`/`master` ni force-push; los hooks lo bloquean.

## Niveles de riesgo (deciden cuánta ceremonia lleva cada ítem)

| Nivel | Áreas (`backend/application`, `backend/domain` y equivalentes) | Requisitos extra |
|---|---|---|
| **T0 crítico** | `cash_register`, `sales`, `finance`, `customer_credit`, `inventory`, `transfers`, `sync`, `security`, `software_updates`, `migrations/`, `installer/` | Spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre copia de la BD |
| **T1 negocio** | `procurement`, `suppliers`, `orders_delivery`, `logistics`, `crm`, `customers`, `loyalty*`, `pricing`, `products`, `meat_processing`, `losses`, `quality`, `hr`, `assets`, WhatsApp | Spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada |
| **T2 bajo** | BI/analytics, UI cosmética, documentación, scripts de diagnóstico | Plan corto, pruebas afectadas |

Un ítem toma el nivel más alto de las áreas que toca.

## Relación con lo que ya existe en el repo

- `CLAUDE.md` (raíz) sigue siendo la guía del proyecto; este SDLC la respeta y no la reemplaza.
- `docs/skills/SPJ_REFACTOR_SKILL.md` (UUIDv7, rutas dentro de `pos_spj_v13.4/`) es autoridad técnica: Design y Build deben cumplirlo.
- `docs/refactor/work_queue.json` y los documentos `docs/refactor/<AREA>-NN_*.md` son historial. Plan los lee para no duplicar trabajo; un ítem SDLC puede referenciar un lote existente en lugar de reabrirlo.
- CI (`.github/workflows/ci-segmented.yml`) y release Windows (`windows-release.yml`, con aprobación en el entorno `production`) son el mecanismo de Test y Deploy; el SDLC no crea pipelines nuevos.
