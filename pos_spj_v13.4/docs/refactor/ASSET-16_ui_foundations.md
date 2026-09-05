# ASSET-16 — UI Foundations (Activos / EAM)

Ejecutado: 2026-09-02. §9-10, §89-90, §103 del prompt maestro.

## Decisión previa: seguir adelante sin la capa de persistencia

Esta fase se construyó después de que 3 rondas consecutivas de esta sesión señalaran que Activos no tenía infraestructura de persistencia ni casos de uso de escritura. El usuario decidió continuar con la UI de todas formas. Dado eso, ASSET-16/17/18 se limitaron deliberadamente al **lado de lectura**: rutas, shell, dashboard y directorio/detalle — todo lo que ya es ejecutable hoy gracias a los QueryServices de ASSET-14 (que dependen solo de Protocol ports, no de infraestructura real). No se construyó ningún formulario de alta/edición (§97) porque eso necesitaría casos de uso de escritura que no existen — ver `ASSET-15_integraciones.md` § "Siguiente fase".

## Qué se construyó

`frontend/desktop/modules/assets/` — nuevo módulo UI, mismo layout que `customers_crm`:

- `view_models.py` — `AssetsCapabilities` (9 flags, uno por grupo del sidebar §8: module_view/activos/mantenimiento/costos/movimientos/control_fisico/documentacion/bajas/control).
- `capability_resolver.py` — mapea cada capability a un permiso granular ya existente de `AssetPermissions` (ASSET-2); no se creó ningún permiso nuevo.
- `assets_routes.py` — 36 rutas (`AssetRoute` dataclass + `visible_routes()`/`grouped_routes()`), la lista canónica completa de §9 (Resumen/Activos/Mantenimiento/Costos y vida útil/Movimientos/Control físico/Documentación/Bajas/Control). Solo 3 tienen página real hoy (ver ASSET-17/18); el resto cae a `ViewState.EMPTY`, nunca a `None`.
- `assets_presenter.py` — `AssetsPresenter`, mismo patrón "bridge delgado" que `CustomerCrmPresenter`: recibe `query_services: dict[str, object]` inyectado, nunca importa/construye un QueryService él mismo, y cada método de lectura degrada a un resultado vacío/cero cuando la clave no está wireada en vez de lanzar — una página siempre tiene algo seguro que renderizar.
- `assets_workspace.py` — el shell (`PageHeader` + `SideNav` + `QStackedWidget`), mismo patrón que `CustomersCrmWorkspace`.

`frontend/desktop/components/icons.py` — se agregaron dos claves nuevas (`Icons.ASSETS`, `Icons.MAINTENANCE`), edición aditiva de bajo riesgo al catálogo compartido, mismo patrón que cada módulo anterior ya siguió (TRANSFERS, LOYALTY, etc.).

## No se tocó el menú de producción

`interfaz/menu_lateral.py` y `interfaz/main_window.py` **no se modificaron** — el botón "Activos" existente sigue apuntando al `ModuloActivos` legacy. El nuevo `AssetsWorkspace` es un módulo autocontenido, probado de forma aislada, pero todavía no está conectado a la aplicación real. El corte de menú (reemplazar el legacy) es una decisión de producto que debe pedirse explícitamente, no una consecuencia automática de construir la UI — mismo criterio que otros módulos de este repo (CRM, Fidelidad) ya aplicaron en fases equivalentes.

## Tests

`tests/unit/assets/test_assets_ui_foundations.py` — rutas (cada una referencia una capability real y un permiso real de `AssetPermissions`, ids únicos, sin `module_view` oculta todo, con todas las capabilities muestra las 36), resolver de capacidades, y el presenter (degradación a vacío/cero cuando no hay QueryService wireado, delegación correcta cuando sí lo hay, filtro de directorio por búsqueda/estado).

## Siguiente fase

ASSET-17 — Dashboard (construida en la misma sesión, ver doc propio).
