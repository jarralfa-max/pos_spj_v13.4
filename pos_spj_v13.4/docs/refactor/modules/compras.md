# Módulo COMPRAS (compras_pro.py) — auditoría F7 / Fase A

## Estado: Fase A en curso (multi-tanda)

`compras_pro.py` (~7670 líneas) es el módulo UI más grande y el mayor ofensor
restante de SQL-en-UI. Se extrae por tandas con repos headless + guardrail
ratchet (`tests/architecture/test_compras_guardrails.py`).

## Baseline inicial (medido)

| Patrón | Inicio | Tras tanda 1 |
|---|---|---|
| `.execute` (SQL) | 50 | **0** ✅ |
| INSERT / UPDATE / DELETE | 2 / 14 / 1 | **0 / 0 / 0** ✅ |
| commit | 5 | **0** ✅ |
| CREATE TABLE (en UI!) | 2 | **0** ✅ → migración 111 |

> **MÓDULO CERRADO:** `compras_pro.py` no ejecuta SQL ni posee transacciones.
> Lo único restante (`uc.execute()`) son ejecuciones de use case.

## Tanda 2 — cluster lecturas QR/contenedores ✅

7 lecturas → `QrContainersReadRepository` (PyQt-free, 7 tests headless):
`search_containers`, `get_container_by_code`, `get_container_code`,
`list_child_containers`, `get_container_products`, `get_container_for_reception`,
`get_container_products_for_reception`. Devuelve `dict(row)` → el consumo
`r["col"]` de la UI queda intacto.

## Tanda 3 — lookups de compra ✅

5 lecturas añadidas a `ComprasReadRepository` (+5 tests headless):
`get_config_value` (IVA, configuraciones/settings), `get_avg_cost`
(inventario_actual), `find_product_for_purchase`, `list_purchase_templates`,
`get_template_items`. Sitios: `_get_iva_rate`, `_costo_compra_producto`,
`_qr_agregar_producto_manual`, plantillas sidebar (cargar/poblar).

## Tanda 4 — recepción / docs-ERP / recetas ✅

6 lecturas añadidas a `ComprasReadRepository` (+7 tests headless):
`get_supplier_name`, `get_purchase_for_reception`, `get_purchase_items_for_reception`,
`list_purchase_requests`, `list_open_purchase_orders`, `products_with_recipe`.
Sitios: `_cargar_po_en_recepcion`, `_cargar_compra_en_recepcion`, `_cargar_docs_erp`
(fallbacks PR/PO), `_detectar_recetas`.

## Tanda 5 — combos + lista pendientes ✅

3 lecturas añadidas a `ComprasReadRepository` (+3 tests): `list_containers_brief`
(combo padre), `list_products_brief` (combo asignar, LIMIT 2000),
`list_pending_containers` (dinámico con filtro). Sitios: `_build_subtab_etiqueta`,
`_build_subtab_asignar`, `_cargar_contenedores_pendientes`.

## Tanda 6 — recepción dinámica + histórico ✅

5 lecturas añadidas a `ComprasReadRepository` (+6 tests): `list_container_history`
(filtros texto/fecha/proveedor), `get_container_history_detail`,
`list_pos_for_reception`, `list_purchases_for_reception`,
`list_assigned_containers_for_reception`. Sitios: `_cargar_historico_qr`,
`_on_hist_row_select`, `_cargar_contenedores_recepcion` ×3.

**Todas las lecturas de UI extraídas.** `ComprasReadRepository` = 24 métodos.

## Lecturas residuales (no-UI / aparte)

- worker thread `run` (619, historial — clase worker con `self._db`)
- `_procesar_recetas` (componentes de receta, fallback) + `_leer_pin` (3-tabla config)

## Schema en UI — cerrado ✅

`_ensure_qr_schema` (CREATE TABLE `contenedores`/`contenedor_productos` + 7 ALTER)
movido a `migrations/standalone/111_qr_containers_schema.py` (registrada en
`engine.py`, idempotente, 26 columnas). El método de la UI quedó como no-op. Las
PK enteras se preservan; su corte a UUID `TEXT` es Fase 2.5 (migración 200).

## Escrituras — tanda 1 ✅

`ComprasWriteRepository` (PyQt-free, sin commit propio) + `ConnectionUnitOfWork`:
- `insert_container` (`_qr_generar_contenedor`)
- `assign_container` + `replace_container_products` (`_qr_guardar_asignacion`:
  UPDATE + DELETE + re-INSERT como una transacción)

4 tests headless, incluido **rollback atómico** (si el re-INSERT falla, el UoW
revierte UPDATE+DELETE juntos). `.execute` 15→11, commit 4→2, INSERT/DELETE → 0.

## Escrituras — tanda 2 (recepción) ✅

`ComprasWriteRepository` + UoW: `mark_container_received`, `set_received_quantity`,
`increase_product_stock`, `update_purchase_status`. Sitios: `_qr_confirmar_recepcion`
(contenedor + cantidad_recibida + stock, el incremento de stock best-effort),
`_confirmar_recepcion_compra` (cierre de estado). Fix: `int(pid)` → str.
6 tests headless (incl. recepción atómica). `.execute` 11→6, commit 2→1.

Nota (regla 12): `increase_product_stock` es UPDATE crudo que **omite
movimientos_inventario**; rutearlo por el servicio canónico de inventario es un
follow-up F6 (cambia comportamiento → su propia protección).

## Escrituras — tanda 3 (cierre) ✅

Últimas extracciones a repos + UoW:
- `_procesar_compra`: `update_purchase_status_by_folio` (UoW) + `get_purchase_id_by_folio`
- `_procesar_recetas`: `get_recipe_components` / `get_recipe_components_v2` (lecturas)
  + `decrease_product_stock` (fallback) envuelto en UoW; ruta primaria sigue usando
  `registrar_salida_produccion`
- worker thread: `_leer_pin` → `get_supervisor_pin`; `_HistorialLoader.run` →
  `list_purchase_history` (tuplas posicionales)

Tests: read 41 + write 9 (incl. recepción/asignación atómicas). Guardrail
`test_compras_ui_has_no_executable_sql_or_commit` bloquea cualquier reaparición.

## F6 — ruteo por servicio canónico de inventario ✅ (regla 12)

La recepción de contenedor (`_qr_confirmar_recepcion`) y el consumo de recetas
(`_procesar_recetas`) ahora registran stock por el **servicio canónico de
inventario** (`container.inventory_service.add_stock` / `deduct_stock`), que
loguea `movimientos_inventario` — espejando la ruta ya probada de recepción PO
(`_confirmar_recepcion_po`, regla 29: una sola ruta). El `increase/decrease_product_stock`
crudo del repo queda **solo como fallback** si el servicio no está disponible
(preserva comportamiento en ese caso).

Cambio de comportamiento: la recepción de contenedor antes hacía `UPDATE existencia`
sin movimiento (bug); ahora genera el movimiento correcto.

> **Limitación de verificación:** son métodos PyQt; no son ejecutables headless
> en este entorno. Mitigación: se espeja código probado (recepción PO), el
> servicio de inventario está testeado aparte, y el fallback al repo (testeado)
> se conserva. Validación manual en la app queda pendiente (checklist).

## Tanda 1 — cluster lecturas proveedor/sucursal ✅

6 lecturas → `ComprasReadRepository` (PyQt-free, 5 tests headless):
`list_active_suppliers`, `list_active_branches`, `get_supplier`,
`recent_purchases_for_supplier`, `cxp_pending_summary`. Cubre los combos de
proveedor/sucursal, panel de info de proveedor, recientes y alerta CxP.

## Pendiente (próximas tandas)

- **QR / contenedores** (~15 lecturas + escrituras): `_qr_*`, `_cargar_contenedores_*`,
  `_mostrar_hijos_contenedor`, recepción QR.
- **Recepción de compra/PO** (`_cargar_po_en_recepcion`, `_confirmar_recepcion_*`).
- **Histórico / docs ERP / plantillas** (lecturas de reporte).
- **Escrituras** (`_procesar_compra`, `_qr_guardar_asignacion`, `_qr_confirmar_recepcion`):
  2 INSERT + 14 UPDATE + 1 DELETE + 5 commit → repos + UoW. Cuidado: tocan
  inventario/compra (integridad). Tests de protección headless antes.
- **`_ensure_qr_schema`**: hace `CREATE TABLE` en la UI — mover a `migrations/`
  (solo migrations modifican schema). Es 2 de los `create_table`.

## Fase B
- Identidad de escritura (`lastrowid` si aplica) + esquema TEXT.
