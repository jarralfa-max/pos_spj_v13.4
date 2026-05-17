# INVENTARIO DE ERRORES BACKEND — Módulo Compras Pro
> Generado: 2026-05-17 | Severidades: CRÍTICO / ALTO / MEDIO / BAJO

---

## Errores de arquitectura (SQL en capa UI)

### ERROR-BE-01 — SQL directo en _cargar_info_proveedor (capa UI)
**Severidad:** ALTO  
**Archivo:** `compras_pro.py` L2642  
**Código actual:**
```python
row = self.container.db.execute(
    "SELECT rfc, telefono, direccion, credito_disponible, condicion_pago FROM proveedores WHERE id=?",
    (prov_id,)
).fetchone()
```
**Problema:** Lógica de consulta de datos del proveedor en la capa UI. No usa el repositorio.  
**Fix correcto:** `self._purchase_repo.get_provider_info(prov_id)` o similar método en `PurchaseRepository`.  
**Fase:** 4

### ERROR-BE-02 — SQL directo en _cargar_recientes_proveedor (capa UI)
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py` L2808  
**Código actual:**
```python
rows = self.container.db.execute(
    "SELECT folio, fecha_doc, total FROM compras WHERE proveedor_id=? ORDER BY fecha_doc DESC LIMIT 5",
    (prov_id,)
).fetchall()
```
**Problema:** Consulta de historial del proveedor en UI.  
**Fix correcto:** `self._purchase_repo.get_recent_by_provider(prov_id, limit=5)`.  
**Fase:** 4

### ERROR-BE-03 — SQL directo en _cargar_alertas_cxp (capa UI)
**Severidad:** ALTO  
**Archivo:** `compras_pro.py` L2856  
**Descripción:** Consulta de cuentas por pagar vencidas directo en UI.  
**Problema:** Mezcla lógica financiera (CXP) dentro del módulo de compras UI.  
**Fix correcto:** Llamar a `FinanceService` o un `CXPRepository` dedicado.  
**Fase:** 4

### ERROR-BE-04 — SQL directo en _poblar_plantillas_sidebar (capa UI)
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py` L2882  
**Descripción:** Consulta de plantillas de compra en UI.  
**Fix correcto:** `self._purchase_repo.get_templates()`.  
**Fase:** 4

### ERROR-BE-05 — SQL directo en _cargar_sucursales_compra (capa UI)
**Severidad:** BAJO  
**Archivo:** `compras_pro.py` L3167  
**Descripción:** Consulta de sucursales en UI.  
**Fix correcto:** `SucursalRepository.get_all()`.  
**Fase:** 4

### ERROR-BE-06 — SQL directo en cargar_proveedores (capa UI)
**Severidad:** BAJO  
**Archivo:** `compras_pro.py` L3190  
**Descripción:** Consulta de proveedores en UI. Volumen potencialmente grande.  
**Fix correcto:** `ProveedorRepository.get_all_active()`.  
**Fase:** 4

### ERROR-BE-07 — SQL directo en _detectar_recetas (capa UI)
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py` L3972  
**Descripción:** Consulta de recetas de producción para detectar si un producto es materia prima.  
**Problema:** Lógica cross-domain (compras + producción) en UI.  
**Fix correcto:** `ProduccionRepository.get_recipes_for_products(product_ids)`.  
**Fase:** 4

### ERROR-BE-08 — SQL directo en _refresh_hist_timeline (capa UI)
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py` L4644, L4668  
**Descripción:** Consulta de datos para línea de tiempo documental (PO, PR, recepción) en UI.  
**Fix correcto:** `PurchaseRepository.get_document_timeline(compra_id)`.  
**Fase:** 9 (historial fase)

### ERROR-BE-09 — _fallback_compra_directa con SQL masivo en UI
**Severidad:** CRÍTICO  
**Archivo:** `compras_pro.py` L5098-5135  
**Descripción:** Método fallback que ejecuta INSERT directo a `compras`, `compra_items`, actualiza `inventario_actual`, escribe en `kardex` — todo en la capa UI, sin pasar por RegistrarCompraUC.  
**Impacto potencial:** Bypass del audit trail financiero. No se llama a `finance_service.registrar_asiento()`. Doble inventario posible si se llama junto al UC.  
**Cuándo se activa:** Solo cuando `RegistrarCompraUC` lanza excepción inesperada.  
**Fix:** Mover a `RegistrarCompraUC` como método de recuperación interna, con audit trail garantizado.  
**Fase:** 4 (PRIORITARIO)

---

## Errores de lógica de negocio

### ERROR-BL-01 — _doc_type sin persistencia entre sesiones
**Severidad:** BAJO  
**Archivo:** `compras_pro.py` L556  
**Descripción:** `self._doc_type = "DIRECT"` en `__init__`. Si el usuario cierra y reabre el módulo, el tipo documental se resetea a DIRECT incluso si había un borrador de PR.  
**Fix:** Leer el tipo documental del borrador al restaurarlo.

### ERROR-BL-02 — IVA no se recalcula al cambiar condición de pago
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py` L2967 (`_on_condicion_changed`)  
**Descripción:** Al cambiar la condición de pago del proveedor, no se fuerza recálculo de totales.  
**Fix:** Al final de `_on_condicion_changed()`, llamar `self._refresh_totals_display()`.

### ERROR-BL-03 — Duplicación de rutas de procesamiento DIRECT
**Severidad:** CRÍTICO  
**Archivo:** `compras_pro.py`  
**Descripción:** Existen dos rutas para procesar una compra directa:
1. `_procesar_compra()` → `RegistrarCompraUC` (ruta correcta)
2. `_fallback_compra_directa()` (bypass sin audit trail — ERROR-BE-09)

Si `RegistrarCompraUC` falla por cualquier razón, el fallback corre SQL directo sin contabilidad.  
**Riesgo:** Compras sin asiento contable en `financial_event_log`.  
**Fix:** El fallback debe llamar a `finance_service.registrar_asiento()` o eliminar el fallback.

### ERROR-BL-04 — PO reception no conectada al inventario en capa ModuloComprasPro
**Severidad:** ALTO  
**Archivo:** `compras_pro.py` + `recepcion_qr_widget.py`  
**Descripción:** El tab "🧾 Recepción PO" en `RecepcionQRWidget` existe (Fase 6) pero el flujo de recepción parcial de PO no está conectado al módulo principal de compras para actualizar el estado de la PO en la sidebar documental.  
**Impacto:** Una PO recibida parcialmente en el tab QR no aparece como "PARCIAL" en el listado de docs del sidebar.  
**Fix:** `ReceivePOAdapter.register_partial_receipt()` debe emitir evento EventBus que el sidebar escuche.  
**Fase:** 8

---

## Errores de datos

### ERROR-DATA-01 — _load_erp_docs_cache sin caché de invalidación
**Severidad:** BAJO  
**Archivo:** `compras_pro.py` L1918  
**Descripción:** `_load_erp_docs_cache()` carga todos los docs desde UC/DB cada vez que se llama. No tiene TTL ni invalidación por evento.  
**Impacto:** En sucursales con muchas PRs/POs, la carga puede ser lenta y bloquear el hilo UI (no usa QThread).  
**Fix:** Mover a QThread similar a `_HistorialLoader`, o cachear con invalidación por EventBus.  
**Fase:** 4

### ERROR-DATA-02 — _get_iva_rate sin recarga forzada
**Severidad:** BAJO  
**Archivo:** `compras_pro.py` L575-600  
**Descripción:** `_get_iva_rate()` cachea el resultado en `_iva_rate_cached`. Si el administrador cambia la tasa de IVA en configuraciones, el módulo seguirá usando el valor viejo hasta reiniciar.  
**Fix:** Invalidar caché en `_on_refresh()` cuando `event_type == "CONFIGURACION_ACTUALIZADA"`.

---

## Estado de tests de backend

| Test | Archivo | Estado |
|------|---------|--------|
| `test_purchase_cancel_flow.py` | tests/purchases/ | Existente |
| `test_purchase_document_states.py` | tests/purchases/ | Existente |
| `test_purchase_finance_effects.py` | tests/purchases/ | Existente |
| `test_purchase_inventory_effects.py` | tests/purchases/ | Existente |
| `test_purchase_lot_creation.py` | tests/purchases/ | Existente |
| `test_purchase_repository.py` | tests/ | Existente |
| `test_uc_compra.py` | tests/ | Existente |

**Pendiente:** Test específico que verifique que `_fallback_compra_directa` llama a `finance_service.registrar_asiento()`.
