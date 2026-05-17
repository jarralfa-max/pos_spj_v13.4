# AUDITORÍA REAL — Módulo Compras Pro
> Generada: 2026-05-17 | Base: compras_pro.py 5138 líneas + recepcion_qr_widget.py 2234 líneas

---

## 1. Estructura de clases

### Clases en compras_pro.py

| Clase | Línea | Rol |
|-------|-------|-----|
| `_PurchaseKPICard` | 84 | Card KPI reutilizable (patrón _InvKPICard) |
| `_DialogItemCompra` | 210 | Dialog de edición de ítem en carrito |
| `_ConfirmDestructiveDialog` | 350 | Confirmación de acciones destructivas |
| `_PINDialog` | 411 | Solicitud de PIN para acciones privilegiadas |
| `_HistorialLoader` | 501 | QThread para carga async del historial |
| `ModuloComprasPro` | 535 | Clase principal del módulo UI |

### Clases en recepcion_qr_widget.py

| Clase | Línea | Rol |
|-------|-------|-----|
| `RecepcionQRWidget` | 51 | Widget completo de recepción con QR |

---

## 2. Mapa de tabs

### Tabs externas (ModuloComprasPro._build_ui, L722-730)

```
Línea 722: "🛒 Compra Tradicional"   → _build_tab_tradicional()
Línea 726: "📦 Recepción con QR"     → _build_tab_qr() (contiene RecepcionQRWidget)
Línea 730: "📋 Historial de Compras" → _build_tab_historial()
```

**CORRECTO: 3 tabs. No hay 4ª tab de PO reception en el nivel externo.**

### Tabs internas en RecepcionQRWidget._build_ui (L92-109)

```
L98:  "🏷️ 1. Generar Etiqueta QR"  → _build_tab_generar()
L99:  "📋 2. Asignar Compra"        → _build_tab_asignar()
L100: "📦 3. Recepcionar"           → _build_tab_recepcionar()
L101: "📜 Historial"                → _build_tab_historial()
L102: "🧾 Recepción PO"             → _build_tab_po_recepcion()   ← Fase 6, en su lugar correcto
```

**CORRECTO: La recepción PO está DENTRO del widget QR, no como 4ª tab externa.**

---

## 3. Mapa de métodos (ModuloComprasPro)

### Construcción UI

| Método | Línea | Responsabilidad |
|--------|-------|-----------------|
| `_build_ui` | 704 | Root layout, KPI bar, 3 tabs, apply_spj_buttons |
| `_build_tab_tradicional` | 804 | Splitter 3 columnas |
| `_build_purchase_kpi_bar` | 839 | 5 KPI cards horizontales |
| `_build_provider_card` | 900 | Card proveedor (left/center) |
| `_build_document_card` | 1041 | Card documento (tipo, folio, fecha) |
| `_build_product_search_card` | 1173 | Búsqueda de productos |
| `_build_purchase_items_panel` | 1204 | Tabla de partidas de compra |
| `_build_purchase_totals_footer` | 1355 | Footer de totales |
| `_build_dynamic_action_button` | 1396 | Botón principal de acción (Procesar/Guardar) |
| `_build_quick_products_card` | 1457 | Productos frecuentes |
| `_build_center_column` | 1491 | Columna central (agrupa cards) |
| `_build_tab_qr` | 1544 | Tab QR (instancia RecepcionQRWidget) |
| `_build_documental_toolbar` | 1597 | Columna izquierda: docs ERP (PR/PO) |
| `_build_provider_sidebar` | 2349 | Panel proveedor en sidebar |
| `_build_summary_panel` | 2429 | Panel derecho: totales + acción |
| `_build_stepper_bar` | 2705 | Stepper documental (oculto en modo DIRECT) |
| `_build_doctype_toolbar` | 2999 | Toolbar tipo documento (oculto, backward compat) |
| `_build_draft_dict` | 3517 | Serializa draft actual a dict |
| `_build_tab_historial` | 4051 | Tab historial de compras |
| `_build_hist_kpi_sidebar` | 4356 | Sidebar KPIs del historial |

### Business logic (en capa UI — a migrar en Fase 4)

| Método | Línea | SQL directo | Notas |
|--------|-------|-------------|-------|
| `_cargar_info_proveedor` | 2631 | Sí (L2642) | Consulta datos del proveedor |
| `_cargar_recientes_proveedor` | 2802 | Sí (L2808) | Últimas compras al proveedor |
| `_cargar_alertas_cxp` | 2851 | Sí (L2856) | Alertas de cuentas por pagar |
| `_poblar_plantillas_sidebar` | 2876 | Sí (L2882) | Carga plantillas de compra |
| `_procesar_como_pr` | 3093 | No (delega a UC) | TraditionalPurchaseUC |
| `_cargar_sucursales_compra` | 3163 | Sí (L3167) | Lista de sucursales |
| `cargar_proveedores` | 3187 | Sí (L3190) | Lista de proveedores |
| `_procesar_compra` | 3681 | No (delega a UC) | RegistrarCompraUC |
| `_detectar_recetas` | 3965 | Sí (L3972) | Recetas de producción |
| `_refresh_hist_timeline` | 4592 | Sí (L4644,L4668) | Línea de tiempo del historial |
| `_fallback_compra_directa` | 5098 | Sí (L5111-5135) | Fallback SQL cuando UC falla |

---

## 4. Capas y delegación

### Estado actual de delegación

```
UI (compras_pro.py)
  ├── _procesar_compra()         → RegistrarCompraUC (OK ✅)
  ├── _procesar_como_pr()        → TraditionalPurchaseUC (OK ✅)
  ├── SQL directo en:
  │   ├── _cargar_info_proveedor()      ← debe → PurchaseRepository
  │   ├── _cargar_recientes_proveedor() ← debe → PurchaseRepository
  │   ├── _cargar_alertas_cxp()         ← debe → FinanceService / CXPRepository
  │   ├── _poblar_plantillas_sidebar()  ← debe → PurchaseRepository
  │   ├── _cargar_sucursales_compra()   ← debe → SucursalRepository
  │   ├── cargar_proveedores()          ← debe → ProveedorRepository
  │   ├── _detectar_recetas()           ← debe → ProduccionRepository
  │   ├── _refresh_hist_timeline()      ← debe → PurchaseRepository
  │   └── _fallback_compra_directa()    ← fallback, usar solo en emergencia
  └── _load_erp_docs_cache()     → PurchaseRequestUC + PurchaseOrderUC (OK ✅)
```

### Repositorios disponibles

| Repositorio | Archivo | Estado |
|-------------|---------|--------|
| `PurchaseRepository` | `repositories/purchase_repository.py` | ✅ Existe |
| `PurchaseOrderRepository` | `repositories/purchase_order_repository.py` | ✅ Existe |
| `PurchaseRequestRepository` | `repositories/purchase_request_repository.py` | ✅ Existe |

### Use Cases disponibles

| UC | Archivo | Estado |
|----|---------|--------|
| `RegistrarCompraUC` | `application/use_cases/registrar_compra_uc.py` | ✅ Existe |
| `TraditionalPurchaseUC` | `application/purchases/traditional_purchase_uc.py` | ✅ Existe |
| `PurchaseRequestUC` | `application/purchases/purchase_request_uc.py` | ✅ Existe |
| `PurchaseOrderUC` | `application/purchases/purchase_order_uc.py` | ✅ Existe |
| `ReceivePOAdapter` | `application/purchases/receive_po_adapter.py` | ✅ Existe |

---

## 5. Atributos de instancia críticos

### Atributos del carrito y proveedor

```python
self.carrito_compra: list[dict]    # Items actuales en compra
self._doc_type: str                # "DIRECT" | "PR" | "PO"
self._prov_id: int | None          # ID proveedor seleccionado
self._prov_nombre: str             # Nombre proveedor display
```

### Atributos UI (widgets críticos con nombre esperado por business logic)

```python
# Proveedor
self._cmb_proveedor          # QComboBox — selector proveedor
self._inp_rfc                # QLineEdit (disabled) — RFC proveedor
self._inp_tel                # QLineEdit (disabled) — Teléfono
self._inp_dir                # QLineEdit (disabled) — Dirección
self._inp_cred               # QLineEdit (disabled) — Crédito disponible
self._cmb_cond_prov          # QComboBox — condición de pago del proveedor
# Alias backward-compat:
self._lbl_rfc = self._inp_rfc
self._lbl_tel = self._inp_tel
self._lbl_dir = self._inp_dir
self._lbl_cred_disp = self._inp_cred
self._lbl_cond_disp = self._cmb_cond_prov

# Documento
self.txt_factura             # QLineEdit — referencia/folio
self._date_factura           # QDateEdit — fecha documento
self.cmb_sucursal_destino    # QComboBox — sucursal destino
self._cmb_moneda             # QComboBox — moneda
self._cmb_prioridad          # QComboBox — prioridad
self.txt_solicitante         # QLineEdit — solicitante
self.txt_notas               # QPlainTextEdit — notas

# Tabla de partidas
self.tabla                   # QTableWidget — partidas de compra

# Totales
self._lbl_subtotal           # QLabel — subtotal display
self._lbl_iva                # QLabel — IVA display
self._lbl_descuento          # QLabel — descuento display
self._lbl_flete              # QLabel — flete display
self._lbl_total_grande       # QLabel — total principal
self._spin_flete             # QDoubleSpinBox — oculto, backward compat
self._spin_otros             # QDoubleSpinBox — oculto, backward compat

# Widgets ocultos backward-compat (C++ GC guard)
self._hidden_doctype_toolbar # QWidget oculto
self._hidden_stepper         # QWidget oculto
self._sidebar_prov_search    # QLineEdit oculto
self._sidebar_prov_list      # QListWidget oculto
self._sidebar_templates_list # QListWidget oculto
self._sidebar_recent_list    # QListWidget oculto
self._lbl_recientes_empty    # QLabel oculto
```

---

## 6. Flujo documental soportado

```
DIRECT → (_doc_type="DIRECT") → _procesar_compra() → RegistrarCompraUC
PR     → (_doc_type="PR")     → _procesar_como_pr() → TraditionalPurchaseUC
PO     → (selección en sidebar) → _on_doc_item_clicked() → [pendiente Fase 6]
```

### Flujo ERP completo (objetivo Fase 7)

```
CAPTURAR → SOLICITUD (PR) → APROBAR PR → GENERAR PO → RECIBIR (QR/PO tab) → INVENTARIO → CXP
```

---

## 7. Métricas

| Métrica | Valor |
|---------|-------|
| Total líneas compras_pro.py | 5138 |
| Total líneas recepcion_qr_widget.py | 2234 |
| Total métodos en ModuloComprasPro | ~148 |
| Métodos con SQL directo | ~9 |
| Métodos que delegan a UC | ~3 |
| Tests existentes en tests/purchases/ | ~22 archivos |
| Atributos de instancia críticos | ~45+ |
| Tabs externas | 3 (correcto) |
| Tabs internas QR | 5 (correcto) |
