# Módulo COMPRAS (compras_pro.py) — auditoría F7 / Fase A

## Estado: Fase A en curso (multi-tanda)

`compras_pro.py` (~7670 líneas) es el módulo UI más grande y el mayor ofensor
restante de SQL-en-UI. Se extrae por tandas con repos headless + guardrail
ratchet (`tests/architecture/test_compras_guardrails.py`).

## Baseline inicial (medido)

| Patrón | Inicio | Tras tanda 1 |
|---|---|---|
| `.execute` | 50 | **44** |
| SELECT | 48 | 42 |
| INSERT / UPDATE / DELETE | 2 / 14 / 1 | 2 / 14 / 1 |
| commit | 5 | 5 |
| CREATE TABLE (en UI!) | 2 | 2 |

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
