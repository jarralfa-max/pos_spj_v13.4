# ASSET-20 — Responsive / Touch (Activos / EAM)

Ejecutado: 2026-09-02. §100-102 del prompt maestro.

## Estado honesto: no existe un sistema formal de densidad compact/comfortable/touch

`frontend/desktop/design_system/` no tiene ningún sistema de perfiles `compact`/`comfortable`/`touch` en ningún lado del repo — es aspiracional (§101 del prompt maestro lo pide: botón principal 52-56px, input 48-52px, fila de tabla 48-56px en modo touch), pero ni siquiera `customers_crm` (el módulo más grande y reciente refactorizado antes que Activos) lo implementó; su propia documentación (`docs/refactor/CRM-14_ui_foundations.md`) ya concluyó lo mismo: "Inventing a new cross-cutting DensityProvider unilaterally for one module was out of scope." Esta fase llega a la misma conclusión por el mismo motivo — un sistema de densidad táctil real necesitaría tocar cada botón/input compartido del Design System, una decisión que no le corresponde a un módulo individual tomar unilateralmente.

## Qué sí se hizo

**Verificar y fijar con tests el único lever responsive real que existe**: `AssetsWorkspace` (ya construido en ASSET-16) usa `PageHeader(compact=...)` + un colapso de ancho de `SideNav` por debajo de `ResponsiveBreakpoints.COMPACT` (1366px) — exactamente el mismo mecanismo que `customers_crm_workspace.py` ya usa. Esta fase:

1. Confirma que el workspace renderiza sin errores en las 4 resoluciones que nombra §100 (1366×768, 1440×900, 1600×900, 1920×1080) — **ninguna de las 4 está por debajo del umbral COMPACT compartido** (1366 no es `< 1366`), así que las 4 renderizan con el nav en ancho completo (240px). Se documenta y prueba explícitamente, no se asume.
2. Confirma que el colapso SÍ funciona por debajo del umbral (probado en 1200×800: nav baja a 180/160px) — demuestra que el lever es real, no decorativo.
3. Agrega verificación de accesibilidad (§104): `AccessibleName` en el workspace, el `SideNav`, el `QStackedWidget`, y en los campos interactivos del directorio (`SearchInput`, `StandardTable`) — ya estaban puestos desde ASSET-16/18, esta fase los deja cubiertos por test en vez de solo "confiados".

## Explícitamente fuera de alcance

No se creó ningún `DensityProvider`, no se ajustó ningún tamaño mínimo de botón/input a 48-56px para un modo táctil — eso requiere una decisión de Design System compartido, no de este módulo. Si se pide en el futuro, debe ser una fase propia que toque `frontend/desktop/design_system/` y afecte a todos los módulos por igual, no un parche local de Activos.

## Tests

`tests/unit/assets/test_assets_responsive_touch.py` — 4 resoluciones nombradas (parametrizado), colapso por debajo del umbral, ancho completo por encima, accesibilidad del workspace y de los campos del directorio.

## Siguiente fase

ASSET-21 — Offline (construida en la misma sesión, ver doc propio).
