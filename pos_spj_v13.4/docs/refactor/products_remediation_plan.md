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
| 3 | Crear producto y KPI no cambia | `ProductsView` construye páginas **una sola vez** (`self._built[index]`) y `_on_nav` no llama `refresh()`; no existe señal central `product_data_changed`. El Resumen sólo lee KPIs en su `__init__`. | ⏳ Slice 3 |
| 4 | Producto canónico no aparece en POS | El POS lee `productos` legacy (`core/services/sales/product_catalog_query_service.py`, etc.); no hay `PosProductCatalogFacade` que componga Productos+Pricing+Inventario. | ⏳ P0-B |
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
