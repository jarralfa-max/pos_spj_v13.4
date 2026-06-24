# Módulo COMPRAS (compras_pro.py) — auditoría F7 / Fase A

## Estado: Fase A en curso (multi-tanda)

`compras_pro.py` (~7670 líneas) es el módulo UI más grande y el mayor ofensor
restante de SQL-en-UI. Se extrae por tandas con repos headless + guardrail
ratchet (`tests/architecture/test_compras_guardrails.py`).

## Baseline inicial (medido)

| Patrón | Inicio | Tras tanda 1 |
|---|---|---|
| `.execute` | 50 | 44 (t1) → 37 (t2) → 32 (t3) → **26** (t4) |
| SELECT | 48 | 42 → 34 → 29 → **21** |
| INSERT / UPDATE / DELETE | 2 / 14 / 1 | 2 / 14 / 1 |
| commit | 5 | 5 |
| CREATE TABLE (en UI!) | 2 | 2 |

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

## Lecturas restantes (tanda 5 reads)

Listas dinámicas con tarjetas QWidget (`_cargar_contenedores_pendientes`,
`_cargar_contenedores_recepcion` ×3, `_cargar_historico_qr`, `_on_hist_row_select`),
worker thread (`run`/`_verificar`), `_build_subtab_*`, `_procesar_recetas`
(componentes), `_ofrecer_impresion_recepcion`.

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
