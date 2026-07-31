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
| 3 | Crear producto y KPI no cambia | `ProductsView` construye páginas **una sola vez** (`self._built[index]`) y `_on_nav` no llama `refresh()`; no existe señal central `product_data_changed`. El Resumen sólo lee KPIs en su `__init__`. | ✅ Corregido (slice 3, refresh en navegación); señal central `product_data_changed` → P1-A |
| 4 | Producto canónico no aparece en POS | El POS lee `productos` legacy (`core/services/sales/product_catalog_query_service.py`, etc.); no hay `PosProductCatalogFacade` que componga Productos+Pricing+Inventario. | ✅ Corregido (slice 5 facade + slice 6 repunte del lector POS a canónico) |
| 5 | Recetas/Rendimientos piden UUIDs a mano | `recipe_form_dialog`/`yield_form_dialog`/`cutting_form_dialog` usan `QLineEdit` "Producto (id)"/"Unidad (id)" y `QLineEdit` para %/tolerancia. | ⏳ P1-C |

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
- **Pendiente P0-B**:
  - repunte de Compras/Inventario/Transferencias a las búsquedas del slice 4
    (los servicios existen; falta que esas UIs los consuman).

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
