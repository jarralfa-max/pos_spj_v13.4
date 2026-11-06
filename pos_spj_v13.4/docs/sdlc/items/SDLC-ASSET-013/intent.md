# SDLC-ASSET-013 — No hay forma de dar de alta ni editar un activo: falta el formulario por secciones con MoneyInput

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §97, §99 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-011, SDLC-ASSET-012

## Problema
La ruta «Alta de activo» cae en «sección en construcción» y el presentador no tiene métodos de escritura. El legacy permitía registrar equipos con serie, valor, vida útil y ubicación; esa capacidad se perdió.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/assets/assets_workspace.py:134-136`
- `frontend/desktop/modules/assets/assets_presenter.py:16-22` — sin escritura

## Impacto
Funcionalidad operativa perdida (CLAUDE.md, prioridad 0).

## Objetivo
- Formulario con las secciones de §97 que tengan respaldo (identificación, clasificación, adquisición, ubicación), montos con MoneyInput y Decimal, que llama a los casos de uso de SDLC-ASSET-011.
- Prueba de UI que crea y edita un activo contra persistencia real.

## Alcance
- **Incluye:** Formulario de alta y edición.
- **No incluye:** Custodia, garantía y documentos en el formulario (se agregan con sus ítems).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- —

## Preguntas abiertas
- Ninguna por ahora.
