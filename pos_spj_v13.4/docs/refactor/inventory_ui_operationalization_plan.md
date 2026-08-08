# Inventario — Plan de operacionalización de UI (post-auditoría externa)

## 0. Origen

Auditoría funcional externa del módulo de Inventario, recibida el 2026-08-08:

- Repositorio: `jarralfa-max/pos_spj_v13.4`
- Rama auditada: `claude/erp-financial-bounded-context-uqxz6b`
- Referencia: PR #326 (abierta al momento de la auditoría)
- Veredicto: **NO APROBADO COMO MÓDULO OPERATIVO** — backend e infraestructura
  de lectura completos, pero el frontend es casi exclusivamente de consulta;
  faltan comandos/acciones/formularios que conviertan las 21 páginas en
  workflows ejecutables.

Los hallazgos se verificaron contra el código real (no se asumió el reporte
como correcto sin comprobar). Confirmados por lectura directa:

- **P0-01** (`frontend/desktop/modules/inventory/presenter.py`): ~20 métodos
  de lectura, un solo comando (`generate_suggestions`).
- **P0-02** (`modulos/inventario_enterprise.py::_build_presenter`): solo
  `InventoryUseCaseFactory.generate_replenishment_suggestions()` se inyecta;
  ningún otro use case (ajustes, conteos, cuarentena, reservas...) llega al
  presenter aunque el factory ya los expone.
- **P0-03** (`backend/application/inventory/composition.py`): el backend sí
  tiene los builders (`create_adjustment`, `create_count`, `quarantine_stock`,
  `record_temperature_reading`, etc.) — está huérfano de interfaz, no ausente.
- **P0-09** y variante de **P0-06** encontrada en el mismo archivo: `_Session`
  (clase privada) congelaba `user_id`/`branch_id` en el `__init__`, antes de
  que el login pudiera completarse, y — más grave — construía
  `_Session(user_id, branch_id, branch_id)`: **`warehouse_id` recibía
  literalmente `branch_id`**, la violación explícita que CLAUDE.md prohíbe
  ("NO warehouse_id=branch_id"), en el propio composition root de la UI.

El orden de ejecución lo definió el usuario (no es una decisión automática):
empezar por **P0-A — Sesión y composition root**, por ser la base de la que
depende cualquier acción que se agregue después (sin sesión/scope reales,
un botón nuevo mutaría con identidad o alcance incorrectos).

## 1. Pendiente (orden del audit, seguirá con P0-B/C/D/E)

1. ~~P0-A: sesión y composition root~~ — **HECHO (slice 1, abajo)**.
2. ~~P0-B/C: página piloto (Cuarentena) — liberar/disponer~~ — **HECHO (slice 2,
   abajo)**. Pendiente en esa misma página: "Poner en cuarentena" (crear), que
   se difiere a P0-D porque necesita búsqueda canónica de producto.
3. P0-D: integración con Productos (búsqueda canónica, resolución de código de
   barras, nombres en vez de UUID en las tablas) — desbloquea "Poner en
   cuarentena" y el resto de las páginas con creación (Ajustes, Reservas,
   Lotes, Conteos).
4. P0-E: integración entre módulos (refresco por eventos tras venta/compra/
   producción; auditar y corregir `warehouse_id=branch_id` en los bridges de
   Ventas/Compras/Producción — el propio audit señala que ahí también existe).
5. P1: `InventoryUiEventBridge` (refresco reactivo) + pruebas de workflow por
   página (no solo de tablas).

## 2. Slices ejecutados

### Slice 1 — P0-A: sesión viva + fin de `warehouse_id=branch_id` en el shell — HECHO

**Archivos:**
- `modulos/inventario_enterprise.py`
- `frontend/desktop/modules/inventory/presenter.py`
- `tests/integration/inventory/test_inventory_enterprise_session_wiring.py` (nuevo)

**Cambio:**

1. `modulos/inventario_enterprise.py`: se eliminó la clase privada `_Session`
   y el atributo redundante `_live_session`. `ModuloInventarioEnterprise`
   ahora toma `container.session` (la instancia `SessionContext` viva, la
   misma que ve el resto del sistema) y la pasa **directamente** como
   `session_context` del presenter — no se construye ninguna copia. Sin
   `container.session` (arneses de prueba mínimos), queda en `None`: las
   lecturas devuelven vacío y las mutaciones se niegan aguas abajo (política
   real, fail-closed). Esto también resuelve P0-09: un login que completa
   después de construir el widget, o un cambio de sucursal, se observa en
   vivo sin reconstruir nada, porque `SessionContext` se actualiza in-place
   (`set_sucursal`/`set_warehouse`/`set_user`) y el presenter guarda la misma
   referencia.
2. `frontend/desktop/modules/inventory/presenter.py`: `default_branch()` y
   `default_warehouse()` leían `session.branch_id`/`session.warehouse_id` —
   atributos que la `_Session` congelada sí tenía (por eso "funcionaba"), pero
   que **`SessionContext` real no expone** (su API es `active_branch_id`/
   `active_warehouse_id`, ver `core/session_context.py`). Se corrigieron para
   leer primero los campos reales de `SessionContext` (`active_branch_id`,
   `active_warehouse_id`), con fallback a `branch_id`/`warehouse_id` para no
   romper dobles de prueba simples que ya usan esos nombres (p. ej. el
   `_Session` de test en `test_inventory_ui_presenter.py`). Sin este cambio,
   pasar `container.session` real habría dejado `default_branch()` siempre
   vacío (mismatch de atributos), rompiendo todas las lecturas con alcance de
   sucursal.

**Por qué no se tocó `InventoryUseCaseFactory.from_session(...)`:** esa parte
ya estaba correcta — recibía `self._live_session` (la sesión viva real) desde
antes; el bug estaba en que el *presenter* recibía la copia congelada en vez
de esa misma sesión viva. `InventorySessionPermissionChecker` (el checker real
de autorización) ya consume `session.tiene_permiso`/`session.user_id`
directamente, sin pasar por `_Session`.

**Evidencia:**
- `tests/integration/inventory/test_inventory_enterprise_session_wiring.py`
  (2, nuevo — no existía ningún test que construyera
  `ModuloInventarioEnterprise`): confirma `widget._session is
  container.session` (misma instancia, no copia); confirma que sin almacén
  fijado en la sesión `default_warehouse()` queda `""` (nunca cae en la
  sucursal); confirma que `set_sucursal`/`set_warehouse` posteriores a la
  construcción se reflejan sin reconstruir el widget; confirma degradación
  correcta (`None`, sin fabricar) cuando el contenedor no expone `.session`.
- Guardrails existentes (ya cubrían parte de esto, se mantienen en verde):
  `tests/architecture/test_inventory_authorization_fail_closed.py`
  (`test_inventory_ui_has_no_fabricated_identity_fallback` — verifica
  literalmente que `default_warehouse` no caiga en `default_branch()` y que
  no haya fallbacks `or "desktop"/"1"/...`), `test_fase_a_identity_clean_modules.py`,
  `test_inventory_no_silent_pass.py`, `test_inventory_no_legacy_permissions.py`,
  `test_inventory_ui_guardrails.py`, `test_app_container_inventory_canonical_route.py`
  → **58 passed** sin cambios.
- `tests/integration/inventory/test_inventory_ui_presenter.py` (su propio
  doble de sesión usa `branch_id`/`warehouse_id`, cubierto por el fallback) →
  sin cambios.
- Inventario completo (`tests/unit/inventory` + `tests/integration/inventory`):
  `2 failed / 575 passed` (2 pre-existentes — `test_legacy_reader_repoints.py`,
  ajenas; +2 tests nuevos).
- Arquitectura completa desde la raíz del repo: `29 failed / 534 passed`
  (línea base sin cambios; confirmado que `test_no_appcontainer_passed_to_services`
  sigue fallando por `backend/application/logistics/service.py`, sin relación
  con este cambio).
- `tests/integration/test_inventory_functional_phase8.py` (10) y
  `tests/test_fase1_uiux_refresh.py` (3) ya fallaban en la línea base por
  causas ajenas (mismatch int/str de `product_id` legacy; `modulos/productos.py`
  eliminado en el flip de Productos) — confirmado con `git stash` antes/después,
  mismo conjunto de fallas.

**Pendiente de P0-A (no cubierto por esta slice, queda para cuando existan más
comandos):** "prohibir `permissive_for_tests()` en rutas productivas" — hoy
el único comando (`generate_suggestions`) ya usa `InventoryUseCaseFactory`
cuando hay sesión viva; el resto de los `handlers` de Ventas/Producción/Compras
que instancian casos de uso directamente (P0-07) es un hallazgo aparte, fuera
del alcance de "sesión y composition root del shell de Inventario" — se
abordará junto con P0-E (integración entre módulos) o en una slice dedicada.

### Slice 2 — P0-B/C: página piloto Cuarentena — liberar/disponer — HECHO

**Por qué Cuarentena y no Ajustes:** `ReleaseQuarantineUseCase`/
`DisposeQuarantineUseCase` solo necesitan el `id` de una cuarentena ya
existente (visible en la fila seleccionada) — cero dependencia de búsqueda de
producto. `CreateAdjustmentUseCase` (y "Poner en cuarentena", la otra mitad de
esta misma página) sí la necesitan, y el propio audit marca la búsqueda
canónica de producto como P0-D, una fase posterior. Empezar por lo que no
tiene esa dependencia evita construir un formulario con un campo de texto para
`product_id` (el defecto P0-04 que el audit señala) que P0-D tendría que
rehacer.

**Bug descubierto al conectar la fila con el comando:** `QuarantineQueryService
.list_open()` nunca seleccionaba `id` — el `row_ids` de `quarantine_table` usaba
`lot_id or product_id`, que se repiten entre cuarentenas del mismo lote/producto.
Sin el id real, ninguna acción por fila es posible (no hay forma de saber cuál
cuarentena actuar). Se agregó `id` al SELECT y al dict devuelto, y `row_ids`
ahora usa ese id.

**Archivos:**
- `backend/application/inventory/queries/quarantine_query_service.py` — `id`
  agregado al SELECT/dict de `list_open`.
- `frontend/desktop/modules/inventory/view_models.py` — `quarantine_table`
  usa `r["id"]` como `row_ids` en vez de `lot_id or product_id`.
- `frontend/desktop/modules/inventory/presenter.py` — nuevos comandos
  `release_quarantine(quarantine_id)` y `dispose_quarantine(quarantine_id,
  reason="")`, y los parámetros `release_quarantine_uc`/`dispose_quarantine_uc`
  en el constructor (mismo patrón que `generate_suggestions_uc`: si no se
  inyectan, el comando responde "no disponible" en vez de fallar).
- `modulos/inventario_enterprise.py::_build_presenter` — con sesión viva,
  construye `factory.release_quarantine()`/`factory.dispose_quarantine()`
  (autorización RBAC real); sin sesión, cae a los use cases con su default
  `permissive_for_tests()` (mismo patrón que `generate_uc`).
- `frontend/desktop/modules/inventory/dialogs.py` (nuevo) —
  `DisposeQuarantineDialog(FormDialog)`: un campo de motivo (auditado por
  `DisposeQuarantineUseCase`), siguiendo el mismo patrón que
  `ReversalDialog` en Finanzas.
- `frontend/desktop/modules/inventory/pages/quarantine_page.py` — dos botones
  ("Liberar" / "Disponer", `create_secondary_button`/`create_danger_button`)
  gateados por `StandardTable.selected_row_id()`; "Liberar" confirma con
  `ConfirmationDialog`, "Disponer" abre `DisposeQuarantineDialog` (irreversible,
  requiere motivo); ambos llaman al presenter, muestran el resultado con
  `QMessageBox` y refrescan la tabla solo si la operación tuvo éxito.

**El patrón que queda de plantilla para las demás páginas** (tal como pide el
audit): Página (botón + selección de fila) → Diálogo de confirmación/formulario
→ Presenter (comando) → Caso de uso autorizado (`InventoryUseCaseFactory`) →
UoW → Ledger/movimiento de estado + Outbox → (evento — el refresco reactivo
por evento es P1, aquí el refresco es manual post-éxito) → tabla actualizada.

**Evidencia:**
- `tests/integration/inventory/test_inventory_ui_presenter.py`: 8 tests nuevos
  — `TestQuarantineCommands` (release/dispose exitosos con flujo real
  `QuarantineStockUseCase` → presenter → `quarantines()` vacío después;
  ambos comandos rechazan sin selección sin tocar el backend; ambos responden
  "no disponible" si no se inyectó el use case) + `TestPagesSmoke` (clic en
  "Liberar" con fila seleccionada llama al presenter real y la tabla queda en
  0 filas sin necesidad de refresh() manual; sin selección, advierte y NUNCA
  llama al presenter — verificado con `unittest.mock.patch.object`). Además
  `test_quarantines_view_model` ahora confirma que `row_ids[0]` es el id de la
  cuarentena, no el lote. **50 passed** (era 42; +8 nuevos, cero regresiones).
- `tests/integration/inventory/test_inventory_enterprise_session_wiring.py`
  (de la slice P0-A) sigue en verde con los dos use cases nuevos en el
  composition root.
- Guardrails de inventario sin cambios: `test_inventory_ui_guardrails.py`
  (incluye el nuevo `dialogs.py` en el escaneo de SQL/db-access — limpio),
  `test_inventory_authorization_fail_closed.py`,
  `test_app_container_inventory_canonical_route.py`,
  `test_inventory_no_silent_pass.py`, `test_inventory_no_legacy_permissions.py`,
  `test_fase_a_identity_clean_modules.py` → **16 passed**.
- Inventario completo: `2 failed / 583 passed` (2 pre-existentes, +8 nuevos).
- Arquitectura completa desde la raíz del repo: `29 failed / 534 passed`
  (línea base sin cambios).

**Pendiente explícito de esta página** (no ítems perdidos, decisiones
documentadas): "Poner en cuarentena" (crear) difiere a P0-D por la búsqueda de
producto; el refresco reactivo por evento (`INVENTORY_QUARANTINE_RELEASED`, ya
emitido por el use case) es P1 — hoy el refresco es manual post-éxito, que es
correcto pero no reactivo ante cambios de otras pantallas/usuarios.
