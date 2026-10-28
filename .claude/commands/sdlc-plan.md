---
description: "SDLC etapa 1 — Plan: triage de toda la app o un intent puntual (uso: /sdlc-plan triage | /sdlc-plan <problema>)"
argument-hint: "triage [área] | <descripción del problema>"
---

Etapa **Plan** del SDLC de SPJ ERP. Argumento: `$ARGUMENTS`

Lee primero `pos_spj_v13.4/docs/sdlc/README.md` y `pos_spj_v13.4/docs/sdlc/BACKLOG.md`. En esta etapa **no modificas código**: solo lees, ejecutas pruebas y escribes en `docs/sdlc/`.

## Modo A — `triage` (barrido de toda la app)

Objetivo: convertir "todo lo que está mal" en un backlog priorizado de ítems pequeños, cada uno con evidencia.

1. **Línea base de pruebas.** Desde `pos_spj_v13.4/`, ejecuta los segmentos de `.github/workflows/ci-segmented.yml` en este orden y guarda el resumen (pasan/fallan/errores de colección) en `docs/sdlc/baseline/<fecha>.md`:
   `python -m compileall -q .` · `python -m pytest tests/architecture -q` · `python -m pytest tests/unit -q` · `python -m pytest tests/unit/security tests/integration/security -q` · `python -m pytest tests/integration -q`.
   Si un segmento no corre por dependencias faltantes, regístralo como hallazgo (`SDLC-CORE`) en lugar de instalar cosas al azar.
2. **Barrido por bounded context en paralelo.** Lanza subagentes `Explore` (uno por grupo) sobre `backend/`, `frontend/`, `modulos/`, `core/`, `migrations/`, `sync/`, `installer/`. Grupos sugeridos: (a) caja/ventas/crédito/finanzas, (b) inventario/transferencias/compras/producción/mermas, (c) sync/seguridad/permisos/sesiones/actualizador/instalador, (d) CRM/lealtad/pedidos/WhatsApp, (e) BI/UI/configuración. Pide a cada uno: defectos con ruta:línea, `NotImplementedError`/stubs/`TODO`, SQL en UI, duplicaciones de servicios o de fuente de verdad, IDs no UUIDv7 (ver `docs/skills/SPJ_REFACTOR_SKILL.md`), escrituras directas entre contextos, operaciones de dinero sin asiento balanceado. Solo conclusiones con evidencia, sin volcar archivos.
3. **Trabajo previo.** Lee `docs/refactor/work_queue.json` y los `*_validacion_final*`/`*_final_validation*` de `docs/refactor/` y `docs/audits/`. Un problema ya cubierto por un lote `DONE` solo entra si hay evidencia nueva de regresión; uno `IN_PROGRESS` se referencia, no se duplica.
4. **Consolidar.** Agrupa hallazgos que comparten causa raíz. Cada ítem debe poder resolverse en una rama con un PR revisable (si no, divídelo).
5. **Escribir.** Por cada ítem: fila en `BACKLOG.md` (etapa `intent-borrador`) y `docs/sdlc/items/<ID>/intent.md` desde `_templates/intent.md`. Prioridad: P0 = pérdida de dinero/datos, duplicados, seguridad o app que no arranca; P1 = flujo de negocio roto; P2 = deuda que bloquea arquitectura; P3 = resto. Nivel de riesgo según la tabla del README.
6. Si `$ARGUMENTS` trae un área (`triage CASH`), limita el barrido a esa área.

## Modo B — un problema puntual

1. Actúa como analista: si la descripción es ambigua, hazme hasta 3 preguntas concretas antes de escribir.
2. Reproduce o localiza el problema en el código y en las pruebas; reúne evidencia.
3. Busca en `BACKLOG.md`, `work_queue.json` y `docs/refactor/` si ya existe; si existe, actualiza ese ítem en vez de crear otro.
4. Crea `docs/sdlc/items/<ID>/intent.md` y su fila en el backlog.

## Al terminar

- Resume: cuántos ítems por prioridad y nivel, los 10 primeros, y las preguntas abiertas.
- Haz commit solo de `docs/sdlc/` con mensaje `sdlc(plan): …`.
- Detente. El siguiente paso es que yo apruebe intents (cambiando su estado a `intent-aprobado`) y ejecute `/sdlc-design <ID>`.
