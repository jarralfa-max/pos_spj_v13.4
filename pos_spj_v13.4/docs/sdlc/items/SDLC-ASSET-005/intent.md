# SDLC-ASSET-005 — El menú interno de Activos ignora el permiso de cada ruta

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §9, §71–§81 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Cada ruta de Activos declara `required_permission`, pero `visible_routes` filtra solo por la capacidad del grupo. Con `ACTIVOS.ver` se ven «Alta de activo» (pide `ACTIVOS.crear`), Categorías, Ubicaciones y Configuración (piden ver configuración) y Custodia. Hoy esas rutas son marcadores, pero cuando tengan pantallas operativas quedarían abiertas a quien no debe.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/assets/assets_routes.py:180-186` — «Return routes authorized by UI capabilities, not raw route permissions» (*verificado directamente*)
- `assets_routes.py:62-64` — `assets.create` con `AssetPermissions.CREATE` (*verificado directamente*)
- `assets_routes.py:68-79,175-177` — categorías, ubicaciones, custodia, configuración
- `capability_resolver.py:53` — `assets.settings` se rige por AUDIT_VIEW (ruta exacta en el módulo de Activos, no verificada)
- `tests/unit/assets/test_assets_ui_foundations.py:37` — solo comprueba que el código existe

## Impacto
Seguridad en UI (la autorización real debe estar en backend, SDLC-ASSET-011). Bajo hoy; obligatorio antes de habilitar escrituras.

## Objetivo
- Una ruta solo se ve si el usuario tiene su `required_permission`.
- Prueba por ruta con un usuario que solo tiene `ACTIVOS.ver`.

## Alcance
- **Incluye:** Filtro de rutas y pruebas.
- **No incluye:** Siembra de permisos (SDLC-ASSET-006).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria SET-26 (barra lateral mostraba todo a cualquiera, mismo patrón)

## Preguntas abiertas
- Ninguna por ahora.
