# Productos — Remediación integral (reproducción + plan por prioridad)

Ejecución del PROMPT MAESTRO de corrección del bounded context **Productos**.
Rama `claude/erp-financial-bounded-context-uqxz6b`. Se empieza **reproduciendo**
los cinco escenarios contra el código real (no documentos), y luego se corrige por
prioridad P0 → P2 en commits acotados (no un commit gigante).

## 1. Reproducción de los 5 escenarios (evidencia en código)

| # | Escenario | Reproducido — causa raíz en código | Estado |
|---|-----------|-------------------------------------|--------|
| 1 | Crear CARCASS sin poder elegir especie | `product_creation_policy.validate_creation` exige `species_id` para `MEAT_PRODUCT_TYPES` (`SpeciesRequiredError`); `ProductFormDialog` **no tenía campo de especie** y `_fields()` nunca enviaba `species_id`. La tabla `species` existía **vacía**, sin read service ni seed. → el alta cárnica siempre fallaba. | ✅ Corregido (slice 1) |
| 2 | Elegir ACTIVE y que se guarde DRAFT | `CreateProductMasterUseCase.execute` fuerza `lifecycle=LifecycleStatus.DRAFT` e **ignora** el estado enviado (correcto), pero el formulario mostraba un `QComboBox` "Estado" con ACTIVE/UNDER_REVIEW → selector engañoso; sin acciones de workflow en la ficha. | ✅ Corregido (slice 2) |
| 3 | Crear producto y KPI no cambia | `ProductsView` construye páginas **una sola vez** (`self._built[index]`) y `_on_nav` no llama `refresh()`; no existe señal central `product_data_changed`. El Resumen sólo lee KPIs en su `__init__`. | ✅ Corregido (slice 3 refresh en navegación + P1-A señal central `product_data_changed` + KPIs enriquecidos + KPIBar update-by-key) |
| 4 | Producto canónico no aparece en POS | El POS lee `productos` legacy (`core/services/sales/product_catalog_query_service.py`, etc.); no hay `PosProductCatalogFacade` que componga Productos+Pricing+Inventario. | ✅ Corregido (slice 5 facade + slice 6 repunte del lector POS a canónico) |
| 5 | Recetas/Rendimientos piden UUIDs a mano | `recipe_form_dialog`/`yield_form_dialog`/`cutting_form_dialog` usan `QLineEdit` "Producto (id)"/"Unidad (id)" y `QLineEdit` para %/tolerancia. | ✅ Corregido (P1-C: selectores canónicos + outputs + totales/simulación) |

Método de reproducción: inspección AST/lectura del formulario, del caso de uso, de
la policy de dominio, del host de navegación y de los diálogos; ejecución de la
suite de Productos y del bootstrap de DB.

## 2. Plan por prioridad (commits acotados)

- **P0-A** — guardado básico: `[slice 1]` especie ✅ · `[slice 2]` lifecycle/badge/acciones ·
  `[slice 3]` refresco de KPIs (señal + refresh en navegación).
- **P0-B** — catálogos consumidores: `PosProductCatalogFacade`, búsquedas
  canónicas (sellable/purchasable/inventory/transferable), asignación sucursal/canal.
- **P0-C** — seguridad fail-closed: autorización sin checker prohibida; sin
  fallbacks `desktop`/`1`.
- **P1-A** — KPIs completos (KPIDTO estados) · **P1-B** — Design System en formularios ·
  **P1-C** — recetas/rendimientos/despiece con selectores + totales + simulación.
- **P2** — navegación completa + retiro de lectores legacy + ratchet vacío.

## 3. Slice 1 — Especie (P0-A) — HECHO

- Migración **169** (`169_species_catalog_seed.py`): siembra idempotente de 12
  especies (bovino, porcino, aves, ovino, caprino, pescado, marisco, …) en
  `species` (`INSERT OR IGNORE` por `code`). Registrada en `engine.py`.
- `SpeciesCatalogQueryService` (read): `list_species/get/species_exists/options`
  (`{id, code, label}` — guarda `species.id`, nunca texto ni UUID a mano).
- `ProductsPresenter.list_species()` + `species_read_factory` cableado en el
  composition root (`modulos/productos_enterprise.py`).
- `ProductFormDialog`: sección **"Clasificación cárnica"** con selector de especie,
  **visible sólo para `MEAT_PRODUCT_TYPES`**; `_fields()` envía `species_id` (None
  en no cárnicos); prefill en edición; validación inline "requieren especie".
- Tests: `tests/integration/products/test_species_catalog_and_form.py` (alta
  cárnica con especie OK; sin especie rechazada; no-cárnico no la exige; selector
  poblado + visibilidad por tipo). Bootstrap siembra 12 especies; `foreign_key_check`
  y `integrity_check` limpios.

Verificación: 53 tests de master/form OK; suite de Productos 598 passed / 1 skipped.
Guardrail `test_productos_guardrails` con 2 fallas **pre-existentes** (drift de
`product_query_service`, ajeno a este slice; confirmado por stash).

## 4. Slice 2 — Ciclo de vida (P0-A) — HECHO

- `ProductFormDialog`: se elimina el `QComboBox` "Estado" editable (§6.1) y se
  reemplaza por un **badge informativo** (`_state_badge`); `_fields()` ya **no
  envía `lifecycle_status`** (el alta nace DRAFT y el update preserva el estado).
  En edición el badge muestra el estado actual traducido.
- `ProductCatalogPage`: acciones de workflow (§6.3) **"Enviar a revisión"** y
  **"Activar"**, gateadas por permiso de edición, delegando en
  `presenter.submit_product/activate_product`. **"Activar"** consulta primero
  `activation_readiness` (§6.4) y, si faltan datos, muestra el panel de
  preparación con la lista de faltantes en vez de un error técnico.
- Tests: `tests/integration/products/test_product_lifecycle_flow.py` — nace DRAFT;
  enviar→activar con segundo usuario; segregación bloquea al creador (§6.5);
  readiness lista faltantes (cárnico sin especie); el formulario muestra badge y
  no dicta el estado.

Verificación: suite de Productos 603 passed / 1 skipped; guardrail con las mismas
2 fallas pre-existentes (ajenas).

## 5. Slice 3 — Refresco de KPIs al navegar (P0-A) — HECHO

- `ProductsView._on_nav`: al re-navegar a una página ya construida se invoca su
  `refresh()` (guardado ante excepción, resiliencia como el host). Así, tras
  crear/activar un producto y volver al Resumen, los KPIs se re-leen **sin
  reiniciar la app** (acceptance 27.4). El Catálogo y el Resumen ya exponen
  `refresh()`.
- Tests: `tests/integration/products/test_products_view_refresh.py` — re-visitar
  dispara `refresh()`; un fallo de refresco no rompe la navegación.
- Pendiente (P1-A): señal central `product_data_changed` para refrescar sin
  navegar y actualización de `KPICard` por `key`.

Verificación: suite de Productos 605 passed / 1 skipped.

Con esto **P0-A queda completo** (especie · lifecycle/badge/acciones/readiness ·
refresco de KPIs). Sigue P0-B (catálogos consumidores + POS canónico).

## 6. P0-B — Catálogos consumidores canónicos (en curso)

- **Slice 4 ✅ (`31b80cf`)** — `ProductSelectionDTO` + servicios de búsqueda
  canónica (§11): `SearchSellable/Purchasable/InventoryManaged/Transferable/
  ProductionInputs/WasteEligible`, con filtros comunes (query/branch/channel/type/
  species/category/active/limit/offset). Sólo leen `products` + `branch_product` +
  `assortments` (nunca `productos` legacy). Tests: capacidad, exclusión
  DRAFT/interno, sucursal, surtido de canal, query+paginación.
- **Slice 5 ✅** — `PosProductCatalogFacade` (§12): compone Productos (identidad/
  flags/barcode/sucursal) + Pricing (`sale_price_amount`) + Inventario
  (`get_availability`) en `PosCatalogItemDTO`, sin meter precio/existencia en el
  agregado `Product`. Tests: composición precio+disponible+barcode, exclusión
  DRAFT/interno/otra-sucursal, precio ausente.
- **Slice 6 ✅** — repunte real del lector POS: `core/services/sales/
  product_catalog_query_service.py` deja de leer `productos` y compone `products`
  + `product_price` BASE + `inventory_balances` (existencia) + `product_categories`
  + `inventory_replenishment_rule` (stock mín.) + `product_images` + `product_barcodes`,
  preservando el contrato de salida de `modulos/ventas.py`. Mapeos confirmados con
  el usuario: `es_compuesto = bundle_allowed OR recipe_allowed`, `es_subproducto =
  product_type ∈ {BY_PRODUCT, CO_PRODUCT}`. Enabler **migración 170** (backfill
  `productos.codigo_barras → product_barcodes` y `imagen_path → product_images`,
  idempotente) para no regresar escaneo/imágenes. **Delistado del ratchet.**
  Tests: `test_pos_catalog_canonical_repoint.py` (contrato dict, flags compuestos/
  subproducto, exclusión DRAFT/interno, barcode+categorías); el legacy
  `test_sales_inventory_stock_consistency.py` se acotó a los componentes que aún
  comparten `inventory_stock` (recetas/reservas). Arquitectura sin nuevas fallas
  (19/402 = baseline); `foreign_key_check`/`integrity_check` limpios.
  *Nota:* `test_productos_guardrails` sigue con su drift pre-existente
  (`product_query_service`); ahora el lector POS reduce uso legacy (dirección
  correcta), snapshot pendiente de refrescar en housekeeping.
- **Slice 7 ✅** — asignación por sucursal/canal (§10): `SetBranchProductUseCase`,
  `CreateAssortmentUseCase`, `SetAssortmentProductUseCase` (autorizados) +
  `BranchAssortmentQueryService` (`branch_assignments`/`channels`/`assortments`) +
  métodos en el presenter + **página "Sucursales y canales"** (búsqueda de producto,
  habilitar/deshabilitar por sucursal, incluir/quitar de surtidos por canal, crear
  surtido). Cableada al composition root y añadida al shell (ahora **7 secciones**,
  la ruta ya no devuelve None — §9). Tests: use cases + query + smoke de la página.
- **Repunte de consumidores a las búsquedas del slice 4** (P0-B):
  - **Compras ✅** — `PurchasePlanningReadService` (`backend/application/queries/
    purchase_planning_query_service.py`) repuntado: `list_forecastable_products` →
    `SearchPurchasableProductsQueryService`; `current_stock` →
    `CanonicalStockReadAdapter`. Delistado del ratchet; fixture del flujo
    forecast→sugerencia migrado a canónico.
  - **Transferencias ✅** — verificado: el módulo **no lee** la tabla legacy
    `productos` (opera con `product_id` UUID; `transfer_query_repository` sin reads
    de producto). Nada que repuntar.
  - **Inventario ⏳** — `inventory_query_service` (6 variantes de query sobre el
    legacy `inventory_stock`) e `inventory_balance_service` son lectores
    multi-query de tamaño *slice-6* (products + inventory_balances + categorías +
    regla de reposición + unidad). Requieren un slice dedicado con migración de
    fixtures y verificación de no-regresión; pendientes.
  - Otros repos de Compras (`compras_read/write_repository`, `purchase_repository`)
    leen `productos` para nombres de línea — repunte análogo al batch 1 (JOIN
    products), pendiente.

## 7. P0-C — Seguridad fail-closed (§21) — HECHO

- **§21.1** `ProductsAuthorizationPolicy` **fail-closed**: sin `PermissionChecker`,
  `require()` **niega** y `has()` devuelve **False** (antes permitía en silencio).
  Se agregan checkers explícitos de prueba `AllowAll/DenyAllProductsPermissionCheckerForTests`
  y el classmethod `permissive_for_tests()`. Los 14 use cases de Productos cambian su
  default de `ProductsAuthorizationPolicy()` (permisivo silencioso) a
  `ProductsAuthorizationPolicy.permissive_for_tests()` (permisivo **explícito**, sólo
  test). En producción el composition root cablea siempre `SessionPermissionChecker`.
- **§21.2** sin fallbacks de identidad: el composition root ya **no inventa**
  `user_id="desktop"` ni `branch_id="1"`; sin sesión quedan en `None` y las
  mutaciones se niegan aguas abajo (la política real exige usuario). El branch de
  no-sesión usa la política permisiva **explícita** de pruebas, no la silenciosa.
- Tests: `test_products_authorization` actualizado (no-checker → fail-closed;
  `permissive_for_tests` permite; DenyAll niega; `has` fail-closed) + regresión
  `test_no_invented_identity_when_no_session` (§21.2). Suite Productos 626 passed;
  arquitectura 19/402 = baseline.
- Pendiente: scope por sucursal/canal end-to-end en las mutaciones (§21.3) y
  segregación en el resto de flujos (ya activa en lifecycle/recipe/yield/import).

## 8. P1-C — Forms cárnicos con selectores (§15/§16/§18) — HECHO (cierra escenario 5)

- **Slice 8 — Recetas** (`recipe_form_dialog`): componentes y **outputs** (§15:
  MAIN/CO/BY-product, merma, pérdida) con producto por `EntitySearchInput`, unidad
  por `SearchableComboBox`, cantidad `DecimalInput`, % `PercentInput`. Ya no hay
  `QLineEdit` de "Producto (id)"/"Unidad (id)".
- **Slice 9 — Rendimientos** (`yield_form_dialog`): outputs con selectores + % min/
  máx + cantidad esperada; **panel en vivo** de total esperado + tolerancia + estado
  (Válido / Fuera de tolerancia con exceso/faltante) y **simulador** informativo
  (entrada de ejemplo → cantidades por output, no crea inventario) (§16/§16.1).
- **Slice 10 — Despiece** (`cutting_form_dialog`): **especie por catálogo**
  (`SearchableComboBox` desde `list_species`, resiliente a preselección fuera de
  catálogo) + producto/unidad por catálogo + medida peso/pieza (§18).
- Tests: `test_recipe_form_selectors`, `test_yield_form_selectors`,
  `test_cutting_form_selectors` (selectores, no UUID; outputs; total/tolerancia/
  estado en vivo; simulación; especie por catálogo) + flujos UI existentes
  adaptados. Suite Productos 638 passed/1 skipped; arquitectura 19/402 = baseline.
- Pendiente §17 (doble medida kg/pza real en rendimientos): la entidad `YieldOutput`
  no lleva aún `expected_piece_ratio`/`weight_unit_id`/`count_unit_id` — requiere
  extensión de dominio + migración (fuera de este slice de UI).

## 9. P1-A — KPIs completos + refresco en vivo (§8) — HECHO

- **§8.3 señal central `product_data_changed`**: `ProductsView` expone la señal;
  al construir cada página la cablea (`set_data_changed_signal`). El Catálogo la
  **emite** tras crear/editar/enviar/activar; el Resumen la **conecta** a su
  `refresh` → los KPIs se actualizan **sin navegar** (además del refresco en
  navegación del slice 3).
- **§8.4 KPIBar update-by-key**: `KPICard.update(dto)` refresca en sitio (título/
  valor/subtítulo/variante) y `KPIBar.set_cards` actualiza las tarjetas existentes
  cuando el conjunto de `key` no cambia (sólo reconstruye si cambia) — evita ciclos
  de `deleteLater` en cada refresco.
- **§8.1/§8.2 KPIs enriquecidos**: 8 tarjetas (activos, borrador, pendientes de
  revisión, cárnicos, internos, incompletos, recetas sin aprobar, rendimientos
  pendientes) con `subtitle`/`tooltip`/`variant` y estados canónicos del `KPIDTO`
  (LOADING/READY/EMPTY/…); `overview_counts` agrega `draft`/`under_review`.
- Tests: `test_kpi_refresh_signal` (update-by-key mantiene los mismos widgets;
  rebuild al cambiar keys; placeholder por estado; la señal central refresca la
  página display). Suite Productos 642 passed; 46 tests que usan KPIBar/KPICard/
  KPIDTO (products+inventory+procurement) verdes.
- Pendiente: `raw_value`/`trend`/`freshness` con datos reales (hoy sólo texto) y
  KPIs adicionales de §8.1 (sin sucursal / sin precio / sin código de barras).

## 10. P1-B — Migración del formulario maestro al Design System (§7) — HECHO

- **`ProductFormDialog` (maestro de productos)**: los catálogos de identidad —
  **unidad base**, **categoría**, **marca** y **especie** — pasan de `QComboBox`
  crudo a `SearchableComboBox` (§7.1/§20): búsqueda por texto + placeholder que
  obliga a elegir, sin listas largas ni texto libre. Guardan siempre el UUID del
  catálogo. El **tipo** se mantiene en `QComboBox` (enum fijo y corto, no catálogo).
- **Placeholder-safe**: nuevo helper `_combo_value(combo)` devuelve
  `current_id()` sólo si `has_selection()`; con el placeholder activo devuelve
  `None` — el maestro nunca guarda el centinela ni una unidad/categoría falsa.
  `_load()` usa `set_current_id(...)` (que cae al placeholder si el valor es None).
- **Botones al Design System**: "Regenerar" (código) e "Imágenes…" usan
  `create_secondary_button(...)` en lugar de `QPushButton` inline.
- Guardrail `test_products_unit_is_uuid::test_form_unit_is_a_catalog_selector`
  actualizado: exige `SearchableComboBox` + `_combo_value(self.base_unit)` (antes
  exigía el `QComboBox` crudo) — el selector de catálogo con búsqueda es ahora el
  contrato canónico.
- Tests: Suite Productos **642 passed/1 skipped** (incluye los flujos de
  categoría/marca/especie/unidad y alta/edición). Arquitectura global constante en
  **55 failed/366 passed** (mismas fallas pre-existentes de Transferencias; cero
  fallas nuevas por este slice).
- Pendiente: base `StandardDialog`/`FormField` para el layout del formulario (hoy
  `QDialog` + `QFormLayout` directos) — refactor de contenedor, no de contrato.

## 11. P2 — Retiro de lectores legacy de `productos` (slice BI) — EN CURSO

P2 vacía progresivamente el *ratchet* de consumidores legacy (`productos`) hasta
llegar a allowlist **vacía**, requisito para el `DROP productos` final. Es
multi-slice y se avanza en commits acotados.

- **Slice BI (este commit)**: repunte de los dos servicios de lectura BI del
  dashboard al maestro/catálogos canónicos, eliminando todo SQL sobre `productos`:
  - `bi_sales_query_service.py`: nombre → `products.name`; categoría (filtro EXISTS,
    `by_category`, `profitability_by_category`) → `product_categories.name` vía
    `products.category_id`; costo por línea → `product_cost.average_cost` (sucursal
    global `branch_id=''`) como *fallback* del costo capturado `costo_unitario_real`.
  - `bi_inventory_query_service.py`: nombre → `products.name`; estado activo →
    `lifecycle_status='ACTIVE'`; costo → `product_cost`; unidad → `units_of_measure`;
    stock mínimo → `inventory_replenishment_rule` (regla global). La existencia sigue
    siendo *flag-gated* (INV-27: `inventory_stock` ↔ `inventory_balances`).
- **Fixtures siguen al código**: `bi_seed.add_product` ahora siembra además el
  maestro `products`, `product_cost`, `inventory_replenishment_rule`,
  `units_of_measure` e `inventory_balances` (con la MISMA identidad `pid`). Esto
  además **arregla 4 tests de inventario BI** que fallaban en baseline (el corte de
  inventario estaba ON pero el seed sólo escribía `inventory_stock`).
- **Ratchet**: allowlist reducida de 55 → **53** (removidos `bi_sales_query_service`
  y `bi_inventory_query_service`); `test_no_new_legacy_productos_consumers` y
  `test_allowlist_has_no_stale_entries` verdes.
- Evidencia: 36 tests BI verdes (incluye los 4 recuperados) + repuntes de inventario
  (`test_legacy_reader_repoints`: BiInventoryRepoint OFF/ON verdes); arquitectura
  global constante **55 failed/366 passed** (mismas fallas pre-existentes de
  Transferencias; cero fallas nuevas).
- Pendiente P2 (siguientes slices): repuntar los ~53 lectores restantes (compras,
  recetas/producción, forecast, delivery, reportes enterprise, repos legacy),
  luego allowlist vacía → migración `DROP productos`.
