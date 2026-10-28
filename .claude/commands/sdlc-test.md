---
description: "SDLC etapa 4 — Test: validación con evidencia + revisión independiente (uso: /sdlc-test SDLC-CASH-003)"
argument-hint: "<ID>"
---

Etapa **Test** para `$ARGUMENTS`. Objetivo: demostrar con evidencia que el spec se cumple y que no se rompió nada más.

## Prerrequisitos

- Estás en la rama `sdlc/<id>` con el trabajo de Build comiteado; etapa `en-test` en `BACKLOG.md`.

## Trabajo

1. **Criterios de aceptación.** Por cada criterio de `spec.md`, localiza la prueba que lo cubre. Si falta, escríbela: debe verificar efectos en BD, idempotencia (reenvío, doble clic, reinicio), autorización y trazabilidad según aplique. Una prueba que solo abre una ventana no cuenta.
2. **Segmentos.** Desde `pos_spj_v13.4/` ejecuta: `python -m compileall -q .`, `python -m pytest tests/architecture -q`, y los directorios de `tests/unit`, `tests/integration` y `tests/e2e` de las áreas tocadas. Para nivel **T0**, ejecuta los segmentos completos de unit, integration y security.
3. **Compara con la línea base** de `plan.md`. Cada fallo se clasifica como *nuevo* (lo corriges y repites) o *preexistente* (se documenta, no se oculta y, si no está en el backlog, se agrega).
4. **Revisión independiente.** Lanza el subagente `sdlc-reviewer` con: el ID, la ruta de `spec.md` y el rango de commits (`git log <base>..HEAD`). No le pases tu razonamiento; debe revisar en frío. Atiende cada hallazgo: corrige (y vuelve al paso 2) o explica por qué no aplica.
5. Escribe `docs/sdlc/items/$ARGUMENTS/test-report.md` con comandos exactos y resultados reales. Lo que requiera equipo físico (impresora, cajón, varias terminales Windows, red local) va en "Pendiente / no verificado" con instrucciones para que yo lo pruebe.
6. Si todo está en verde, etapa → `listo-deploy`. Commit `sdlc(test): $ARGUMENTS`.

## Al terminar

Tabla breve criterio → prueba → resultado, fallos preexistentes, hallazgos del revisor y su resolución. Siguiente: `/sdlc-deploy $ARGUMENTS`.
