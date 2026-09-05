# PROC-23 — UI/UX: Procesamiento Cárnico

Estado: **DONE** dentro de su alcance declarado (primera página funcional
real — Órdenes — con composition root, presenter y wiring completo a los
use cases reales; el resto de `MEAT_PROCESSING_NAV` sigue en el placeholder
de PROC-4; **sin cutover** del botón de sidebar legacy)

## Alcance y decisión de arquitectura

PROC-4 dejó un cascarón de navegación real (sidebar QListWidget, rutas,
permisos, feature flags) pero cada página era
`MeatProcessingPlaceholderPage` — "cero SQL, cero lógica de negocio", su
propia sección "Pendiente" nombraba explícitamente lo que faltaba:
"páginas funcionales (PROC-5+)" y "cutover del menú global — PROC-23/PROC-25".
Con 21 fases de backend ya completas (PROC-2..PROC-22), esta fase construye
la primera página funcional real siguiendo el patrón ya establecido y
probado por Losses (`frontend/desktop/modules/losses/` +
`backend/infrastructure/desktop/losses_factory.py`): un composition root
por módulo (`*ModuleHost`) que el contenedor de la app instancía con
`container.db`/`container.session`, wire de presenters sobre los use cases
reales, y páginas Qt sin SQL ni lógica de negocio.

**Por qué solo Órdenes y no las 19 secciones**: `ProcessingOrder` es el
agregado raíz del que depende el resto del ciclo de vida — es también la
única sección donde ya existe el backend completo end-to-end (crear →
aprobar → liberar → cerrar, cerrando con PROC-22). Construir las 18
secciones restantes en una sola fase habría repetido el mismo patrón 18
veces sin agregar una decisión de diseño nueva; se deja como trabajo
incremental futuro, exactamente la misma disciplina de alcance que cada
fase PROC-* anterior ya aplicó (§19 "sin construir un APS completo", §26
"sin hardcodear", etc.).

**Por qué no hay cutover del botón "Procesamiento Cárnico" del sidebar
global**: `interfaz/menu_lateral.py` sigue lanzando el legacy
`modulos/produccion.py`, sin tocar. Redirigirlo a `MeatProcessingModuleHost`
ahora dejaría sin acceso operativo a las 18 secciones que siguen siendo
placeholder — una regresión funcional real (Regla 0: "NO eliminar
funcionalidad operativa sin migración completa"), aunque ningún archivo se
borre. El cutover, cuando corresponda, es el mismo criterio que Losses ya
demostró (`LOSS_23_LEGACY_REMOVAL_REPORT.md`): primero paridad de páginas,
luego cutover, luego eliminación de legacy — las tres cosas en fases
separadas, no juntas.

## Componentes nuevos

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Query | `backend/application/meat_processing/queries/processing_order_query_service.py` | `ProcessingOrderQueryService` — lectura de solo lectura sobre `ProcessingOrderRepository` (mismo patrón que `ProcessGenealogyQueryService`, PROC-18); ninguna página toca SQL directo. |
| Presentación | `frontend/desktop/modules/meat_processing/view_models.py` | `TableViewModel` — mismo shape que el de Inventory/Losses (duplicado por módulo, no compartido — convención ya establecida en el repo). |
| Presentación | `frontend/desktop/modules/meat_processing/presenters/processing_order_presenter.py` | `ProcessingOrderPresenter` — consultas devuelven `TableViewModel`; comandos devuelven `(ok, message, data)`; cada comando re-valida su propio permiso en el backend (ocultar un botón no es seguridad) — el presenter solo da forma a lo que la página muestra/habilita. |
| Presentación | `frontend/desktop/modules/meat_processing/dialogs.py` | `CreateProcessingOrderDialog` — producto vía búsqueda canónica (`EntitySearchInput`), nunca un UUID tecleado a mano. |
| Presentación | `frontend/desktop/modules/meat_processing/pages/processing_orders_page.py` | `ProcessingOrdersPage` — tabla + acciones (Nueva orden / Aprobar / Liberar / Cerrar), mirror exacto de `frontend/desktop/modules/inventory/pages/adjustments_page.py`. |
| Composición | `backend/infrastructure/desktop/meat_processing_factory.py` | `MeatProcessingModuleHost(MeatProcessingView)` — construye `MeatProcessingAuthorizationPolicy(MeatProcessingSessionPermissionChecker(session))` real (nunca `permissive_for_tests()` en producción), un `context_provider` que arma `MeatProcessingExecutionContext` desde la sesión activa, y un `page_builder` que sirve la página real para `mp_processing_orders` y cae al placeholder de PROC-4 (`build_page`) para todo lo demás. |

Tema JUANIS: ya existe repo-wide (`frontend/desktop/themes/`, paleta de 5
colores base + tokens semánticos derivados) — esta fase no agrega ni
modifica paleta; los componentes reutilizados (`PageHeader`, `StandardTable`,
`create_primary_button`, etc.) ya lo aplican automáticamente.

## Tests

`tests/integration/meat_processing/test_meat_processing_ui_presenter.py`
(13 tests, sin PyQt — el presenter no depende de Qt): listado vacío/con
datos, validaciones de creación (producto/tipo/cantidad faltantes),
segregación de funciones en la aprobación (mismo actor no puede
crear+aprobar, verificado end-to-end a través del presenter), transiciones
antes de tiempo rechazadas, comandos "no disponible" cuando el presenter no
está conectado a un use case.
`tests/integration/meat_processing/test_meat_processing_view_shell.py`
(4 tests, Qt offscreen — ver `tests/conftest.py`): el host construye y
muestra la primera ruta; la ruta de Órdenes sirve la página real; cualquier
otra ruta sigue sirviendo el placeholder; ciclo de vida completo (crear →
refrescar → aparece en la tabla) a través de la página real.

## Pendiente

- Las 18 secciones restantes de `MEAT_PROCESSING_NAV` siguen en
  `MeatProcessingPlaceholderPage` — construcción incremental, una a la vez,
  según se priorice.
- `MeatProcessingModuleHost` no está registrado en `interfaz/main_window.py`
  todavía — nada en la app en ejecución lo instancía hoy; existe y está
  probado, pero no hay forma de abrirlo desde el sidebar global sin cutover
  (ver "Por qué no hay cutover" arriba).
- Badges (`orders_needing_attention`, etc.) del sidebar siguen sin datos
  reales — `MeatProcessingModuleHost` pasa `badges={}` (mismo estado que
  PROC-4 dejó pendiente: "wiring `has_feature`/badges a query services
  reales").
- `ProcessingOrdersPage` no expone snapshot de receta ni las demás acciones
  del ciclo (start/pause/resume/complete de ejecución) — solo
  crear/aprobar/liberar/cerrar; ejecución en tiempo real es una página
  distinta (`mp_active_processing`), todavía placeholder.
