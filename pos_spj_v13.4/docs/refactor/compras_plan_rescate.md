# Plan de rescate por fases — Compras ERP

**Fecha:** 2026-05-17
**Alcance de esta entrega:** solo Fase 0 y Fase 1.

---

## FASE 0 — Auditoría real

**Estado:** completada en esta entrega.

### Archivos de documentación

- `docs/refactor/compras_auditoria_real.md`
- `docs/refactor/compras_ui_errors.md`
- `docs/refactor/compras_backend_errors.md`
- `docs/refactor/compras_qr_no_touch_policy.md`
- `docs/refactor/compras_po_reception_tab_error.md`
- `docs/refactor/compras_plan_rescate.md`

### Hallazgos clave

1. Compras tiene tres tabs principales correctas.
2. Recepción QR contenía una pestaña interna explícita `Recepción PO`; quedó corregida en Fase 2 como submodo de Recepcionar.
3. Compra Tradicional ya intenta layout de tres columnas, pero requiere limpieza UI y tema.
4. `PurchaseService.register_purchase()` es una ruta directa con inventario/finanzas/lotes; PR/PO no deben usarla.
5. Existe SQL directo y fallback de inventario dentro de la UI; debe migrarse gradualmente.
6. Inventario define el patrón visual principal para KPIs, tablas, inputs y botones.

---

## FASE 1 — Correcciones de arranque y no regresión

**Estado:** completada en esta entrega con smoke tests.
**Tipo de cambio permitido:** tests/documentación; no rediseño; no cambio QR; no cambio negocio.

### Tests/smoke tests mínimos

- `tests/purchases/test_compras_module_imports.py`
- `tests/purchases/test_compras_tabs_contract.py`
- `tests/purchases/test_qr_no_extra_po_tab.py`
- `tests/purchases/test_traditional_purchase_smoke.py`

### Contrato validado

- El módulo se puede importar/parsear.
- Existen clases y métodos críticos.
- Hay exactamente tres tabs principales.
- No hay tab principal de recepción PO.
- Compra Tradicional conserva constructor de tres columnas.
- Recepción con QR sigue importable.
- La tab interna PO queda marcada como deuda de Fase 2, no como estándar final.

---

## FASE 2 — Eliminar/reintegrar pestaña incorrecta de recepción PO

**Estado:** completada en esta entrega.

Resultado:

- Se eliminó la pestaña interna `Recepción PO`.
- El contenido útil vive como submodo/panel dentro de `📦 3. Recepcionar`.
- Se agregó selector interno `Origen de recepción: QR / Contenedor | Orden de Compra / PO`.
- No se reescribió el motor QR.
- No se duplicó recepción, inventario, kardex, lotes, CXP, asientos ni eventos.

---

## FASE 3 — Reconstrucción UI de Compra Tradicional

**Estado:** completada en esta entrega.

Resultado:

- Se consolidó el layout de tres columnas reales con `QSplitter` semántico.
- La columna derecha dejó de comportarse como sidebar: crece junto con captura (`setStretchFactor(2, 1)`).
- Se agregaron componentes semánticos Fase 3 (`PurchaseKpiBar`, `PurchaseDocumentToolbar`, `PurchaseCapturePanel`, `PurchaseItemsAndTotalsPanel`, etc.).
- La tabla de partidas y totales permanecen en la derecha.
- Se redujeron estilos manuales en botones de acción rápida y acción principal usando botones estándar.
- No se modificó QR ni negocio de compra directa.

---

## FASE 4 — Limpieza dark/light

**Estado:** pendiente.

Objetivo:

- Eliminar paneles blancos en dark mode.
- Usar objectName/QSS global/tokens.
- Validar contraste en tema claro y oscuro.

---

## FASE 5 — Estabilizar compra directa

**Estado:** ejecutada el 2026-05-17.

Objetivo:

- Proteger compra directa actual antes de tocar rutas documentales.
- Verificar proveedor, productos, carrito, totales, IVA, flete/otros, pago, inventario, CXP/lotes/historial si aplica.

Decisiones ejecutadas en esta fase:

- `RegistrarCompraUC` valida proveedor, sucursal, productos, subtotal, IVA, total y forma de pago antes de tocar `PurchaseService`; además el IVA viaja a `PurchaseService` para persistirse en cabecera.
- `PurchaseService.register_purchase()` cancela el savepoint completo si falla inventario; no debe quedar cabecera/detalle parcial de compra directa.
- `_fallback_compra_directa()` queda como stub bloqueado: no inserta compras, no actualiza inventario y no opera como ruta alterna desde UI.
- No se tocó QR, no se agregaron pestañas y no se separaron rutas PR/PO; eso queda para Fase 6+.

---

## FASE 6 — Separar rutas documentales

**Estado:** ejecutada el 2026-05-17.

Regla:

- DIRECT puede usar `register_purchase()`.
- PR no puede usar `register_purchase()`.
- PO no puede usar `register_purchase()`.
- Recepción PO debe ser la ruta física que afecta inventario.

Decisiones ejecutadas en esta fase:

- `TraditionalPurchaseUC` mantiene `DIRECT → RegistrarCompraUC` y separa `PR → PurchaseRequestUC` / `PO → convertir_a_po()` sin ruta física.
- Se detectó riesgo real de doble inventario en recepción PO porque el adaptador recibía con `inventory_service.add_stock()` y luego reutilizaba la ruta de compra directa. Antes de continuar se documentó y se cambió la trazabilidad para usar `PurchaseRepository.create_purchase()` sin volver a mover inventario, lotes, CXP ni asientos.
- Recepción PO sigue viviendo dentro de Recepción con QR; no se creó pestaña separada ni se tocó motor QR.
- Corrección anti-regresión: si por error aparece una pestaña `Recepción PO`/`PO Reception`, la UI la elimina al construir tabs y mantiene PO como submodo interno.
- La creación/aprobación funcional completa de PR/PO queda para Fase 7; esta fase solo protegió la separación de rutas.

---

## FASE 7 — PR / aprobación / PO en Compra Tradicional

**Estado:** ejecutada el 2026-05-17.

Objetivo:

- Crear PR, enviar a aprobación, aprobar/rechazar, convertir a PO, enviar PO a recepción.
- Sin inventario/CXP/asientos para PR/PO.

Decisiones ejecutadas en esta fase:

- La creación de PR desde Compra Tradicional ahora nace como `PENDIENTE_APROBACION` mediante `RegisterPurchaseCommand.pr_estado_inicial`; no usa la ruta física de compra directa.
- Las acciones del sidebar documental usan los UCs canónicos del contenedor (`uc_purchase_request` / `uc_purchase_order`) para aprobar, rechazar, convertir a PO y enviar PO a Recepción.
- La edición/carga de PR usa datos del UC/repositorio; no agrega SQL nuevo en UI ni afecta inventario/CXP/asientos.
- La recepción PO permanece dentro de Recepción con QR; Fase 7 solo envía la PO a esa ruta, no implementa recepción física.

---

## FASE 8 — Recepción con QR apta para PO

**Estado:** ejecutada el 2026-05-17.

Objetivo:

- Selector origen QR/PO/transferencia dentro de Recepción con QR.
- Adapter PO mínimo que reutilice servicios existentes.
- Recepción parcial/completa con actualización de estado PO.

Decisiones ejecutadas en esta fase:

- El selector de origen en `📦 3. Recepcionar` contiene QR, PO y Transferencia sin crear tabs nuevas.
- La opción Transferencia queda como origen reservado/informativo y no ejecuta inventario desde Compras para evitar duplicar kardex con el módulo Transferencias.
- La ruta PO sigue usando `ReceivePOAdapter` para recepción parcial/completa y actualización de estado; no usa la ruta DIRECT ni una pestaña separada.
- Los guards anti-regresión cubren variantes de título PO/OC/Recibir Orden y remueven cualquier tab accidental.

---

## FASE 9 — Historial documental

**Estado:** pendiente.

Objetivo:

- Mostrar compras, PR, PO y recepciones sin convertir historial en BI.

---

## FASE 10 — Pruebas, limpieza y documentación final

**Estado:** pendiente.

Objetivo:

- Ejecutar suite relevante.
- Limpiar estilos/manuales/código muerto.
- Documentar decisiones finales.
