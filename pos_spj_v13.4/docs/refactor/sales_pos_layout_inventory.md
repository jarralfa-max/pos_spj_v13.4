# Sales/POS — Inventario de layout (SALES-1 / POS-1)

Fecha: 2026-08-16
Fuente: lectura directa de `modulos/ventas.py::init_ui` (lineas 1447-2075) y verificacion
en vivo contra el widget real (`ModuloVentas`), construido headless
(`QT_QPA_PLATFORM=offscreen`) via `tests/visual/golden/sales_pos/`.

> Este documento es un **inventario**, no una propuesta. Cada dimension citada es un valor
> literal ya presente en el codigo (`setFixedHeight`, `setMinimumWidth`, etc.), no una
> recomendacion. Es la base de los tests de `tests/visual/golden/sales_pos/`.

---

## 1. Arbol de widgets (orden real de construccion)

```text
ModuloVentas (QWidget)                          root_layout: QVBoxLayout, margin 0, spacing 0
│
├── cashier_bar  [objectName="posCashierBar"]    QFrame, fixedHeight=48
│   └── QHBoxLayout margin(12,4,12,4) spacing 10
│       ├── "🛒 Punto de Venta"                   posCashierTitle
│       ├── _lbl_cashier_meta                     posCashierMeta (vacio en runtime — ver §3)
│       ├── addStretch(1)
│       ├── "● Abierto"                           posStatusBadge (estatico — ver §3)
│       ├── addSpacing(8)
│       ├── "⚖ Báscula"                           posHWBtn
│       ├── "💳 Terminal"                          posHWBtn (repropuesto — ver §3)
│       └── "📋 Corte Z" → _ir_a_caja()             posCorteBtn
│
└── body (QWidget)                                QHBoxLayout margin(8,8,8,8) spacing 8
    └── splitter [class="main-splitter"]          QSplitter horizontal, handleWidth=3
        │                                          stretchFactor(0)=1, stretchFactor(1)=0
        │                                          setSizes([620, 460])
        │
        ├── panel_izquierdo (splitter.widget(0))   QVBoxLayout spacing 6, margin(5,5,5,5)
        │   ├── search_row [posSearchFrame]        QHBoxLayout margin(8,6,8,6) spacing 6
        │   │   ├── "▦" btn_barcode                 posBarcodeBtn, fixedSize(36,36)
        │   │   ├── txt_busqueda                    posSearchInput, stretch=1
        │   │   ├── "Buscar" btn_buscar              minWidth 72
        │   │   ├── "✕" btn_limpiar_busqueda         deleteBtn, fixedSize(32,32)
        │   │   └── _lbl_scan_state ("LIBRE")        posScanStateWaiting, fixedHeight 22
        │   ├── lbl_scanner_notif (oculto por defecto)  posScannerNotif, fixedHeight 24
        │   ├── category_row_frame [posCategoryRow] QHBoxLayout margin(4,4,4,4) spacing 4
        │   │   ├── _category_scroll                posCategoryScroll, fixedHeight 32, stretch=1
        │   │   ├── "⊞" _btn_view_grid               posViewIconBtn, fixedSize(28,28), checked
        │   │   └── "☰" _btn_view_list               posViewIconBtn, fixedSize(28,28), DISABLED
        │   │                                        ("Vista de lista (próximamente)")
        │   └── group_productos (QGroupBox, stretch=1)
        │       └── scroll_area_productos            minimumHeight 300
        │           └── grid_productos (QGridLayout) spacing 10, margin(10,10,10,10)
        │               └── ProductCard × N          fixedSize(175, 198)
        │                                             image area 175×85, stock-colored border
        │
        └── panel_derecho (splitter.widget(1))     minimumWidth=380, maximumWidth=600
            │                                        QVBoxLayout spacing 0, margin 0
            ├── cart_header [posCartHeader]         QFrame, fixedHeight 42
            │   ├── "CARRITO DE COMPRA"              posCartHeaderTitle
            │   ├── "⋮" btn_cart_menu                 posCartIconBtn, fixedSize(28,28)
            │   └── "🗑" btn_cart_clear → cancelar_venta()  posCartIconBtn, fixedSize(28,28)
            ├── _carrito_group [posCartGroup]       QGroupBox, Expanding/Expanding, minH 160
            │   ├── tabla_compra                     posCartTable, 7 cols, rowHeight 48,
            │   │                                     hidden when cart empty
            │   └── _lbl_cart_empty                  posCartEmpty, shown when cart empty
            ├── group_cliente [posClientFrame]      Expanding/Maximum, margin(12,6,12,6)
            │   ├── "Cliente"                         posClientSectionLabel
            │   ├── txt_cliente (oculto, maxH 0)      scanner target when context="cliente"
            │   ├── _client_search_row (oculto)       🔍/➕/✕ (buscar/agregar/limpiar cliente)
            │   ├── _client_display_row               👤 + lbl_nombre_cliente + loyalty tier
            │   │                                     badge + "Cambiar" toggle (posClientChangeBtn)
            │   └── info2 row                         lbl_puntos_cliente + lbl_telefono_cliente
            ├── totals_card [posTotalsCard]         Expanding/Maximum, margin(12,8,12,8)
            │   ├── row_sub: "Subtotal" / value
            │   ├── _row_discount_widget (oculto por defecto): "Descuento" / value
            │   ├── _row_iva_widget (oculto por defecto): "IVA (16%)" / value
            │   ├── divider (QFrame.HLine)
            │   └── row_total: [card_peso(oculto)] [pts-a-ganar card] [card_comision(oculto)]
            │                  ── stretch ── "TOTAL" lbl_total
            ├── _banner_sin_impresora (oculto por defecto, banner-warning)
            ├── desc_frame [posDiscountBar]         Expanding/Maximum, margin(8,5,8,5)
            │   └── "5%" "10%" "15%" "20%" (danger) + "Personalizado" (primary), minH 30
            ├── group_acciones [posCobrarFrame]     Expanding/Maximum, margin(8,6,8,6)
            │   ├── btn_cobrar "💳 COBRAR $0.00" F9   btnCobrarPOS, class=success,
            │   │                                     fill_parent=True, Expanding/Fixed, minH 48
            │   └── row_secondary (QHBoxLayout)
            │       ├── btn_suspender "⏸ Suspender" F6   class=warning, minH 34
            │       ├── btn_reanudar "▶ Reanudar (0)" F7  class=primary, minH 34
            │       └── btn_cancelar "✕ Cancelar" F8      class=danger, minH 34
            └── group_utilidad [posUtilBar]         Expanding/Maximum, margin(8,4,8,4)
                ├── btn_devolucion "↩ Devolución" F10   posUtilBtn, minH 30, DISABLED by default
                ├── btn_factura "🧾 Factura" F11         posUtilBtn, minH 30, DISABLED by default
                └── btn_reimprimir "🖨️ Reimpr." F12      posUtilBtn, minH 30, DISABLED by default
```

Nota de orden vertical del panel derecho (importante, difiere de la lista abstracta del master
prompt §1): el orden REAL de construccion es
`cart_header → carrito_group → group_cliente → totals_card → banner → discount_bar →
group_acciones (Cobrar+Suspender/Reanudar/Cancelar) → group_utilidad`
— es decir, **el carrito aparece antes que el bloque de cliente**, no despues como sugiere el
orden de bullets de la seccion 1 del master prompt. Este documento registra la realidad; la
seccion 1 del master prompt es una descripcion de alto nivel del contenido esperado, no un
mandato de order exacto lockeado. `tests/visual/golden/sales_pos/test_pos_customer_panel_position.py`
protege el orden REAL (cliente debajo del carrito), no el de la lista del prompt.

---

## 2. Medidas y proporciones (valores literales del codigo)

| Elemento | Valor |
|---|---|
| `cashier_bar` altura | 48px fijo |
| `panel_derecho` ancho | min 380px, max 600px |
| Splitter tamano inicial | `[620, 460]` (izq/der), `handleWidth=3` |
| Splitter stretch factors | izquierdo=1 (absorbe ancho extra), derecho=0 (ancho preferido) |
| `ProductCard` | 175×198px normal, 182×206px en hover/seleccion (zoom ~4%) |
| `ProductCard` imagen | 175×85px |
| `cart_header` altura | 42px fijo |
| `_carrito_group` altura minima | 160px |
| `tabla_compra` fila | 48px (`verticalHeader().setDefaultSectionSize/MinimumSectionSize`) |
| `tabla_compra` altura minima | `3 * 48 + 28` = 172px |
| `tabla_compra` columnas | 7: Producto(stretch) / Cant.(46) / Precio(58) / Desc.(52) / Total(62) / (30) / (30) |
| `btn_cobrar` altura minima | 48px |
| `btn_suspender/reanudar/cancelar` altura minima | 34px |
| `btn_devolucion/factura/reimprimir` altura minima | 30px |
| Botones de descuento rapido altura minima | 30px |
| `_category_scroll` altura fija | 32px |
| `scroll_area_productos` altura minima | 300px |
| `_lbl_scan_state` altura fija | 22px |

Verificado en vivo (widget real, headless) a 1366×768: ambos paneles reciben ancho > 0, el panel
derecho respeta su rango [380, 600]; a 1920×1080 el ancho extra va al panel izquierdo (catalogo),
el panel derecho se mantiene ≤600px — confirmado por
`tests/visual/golden/sales_pos/test_pos_layout_at_{1366x768,1920x1080}.py`.

---

## 3. Hallazgos de fidelidad (bindings reales vs. apariencia)

Estos NO son cambios estructurales — son notas sobre que partes del layout actual muestran
datos reales vs. texto/estado decorativo. Documentados aqui porque una futura fase de SALES-N
tendra que re-cablearlos SIN mover ni un pixel del layout que los contiene.

1. **`_lbl_status_badge` ("● Abierto") es texto estatico.** Se fija una sola vez en
   `init_ui` (linea 1470) y no se reasigna en ningun otro punto del archivo (verificado por
   busqueda de todas las asignaciones `.setText` sobre este label). No refleja
   `finance_service.get_estado_turno()` en tiempo real.
2. **El boton "💳 Terminal" (`_btn_terminal_hw`) esta re-propuesto para mostrar el nombre de
   sucursal**, no el estado de una terminal de pago — ver `set_sucursal`/`on_branches_changed`
   (lineas ~1326-1331, ~1372-1373). No existe integracion real de terminal de tarjeta en este
   repositorio (confirmado en `docs/refactor/SALES-0_auditoria.md` §Pagos).
3. **Los badges F6-F12 pintados en los botones (`_FKeyButton`) son decorativos.** No existe
   ningun `QShortcut` ni manejo de `Qt.Key_F6..F12` en `modulos/ventas.py::keyPressEvent`
   (que solo gestiona buffer de scanner/Enter/Tab) ni en ningun otro archivo del repositorio
   (busqueda repo-wide sin resultados fuera de `modulos/ventas.py`). Presionar F9 hoy NO activa
   Cobrar.
4. **El tema claro/oscuro no esta realmente cableado.** `modulos/ventas.py` importa
   `GestorTemas` desde `config.py`, pero `config.py` no define esa clase — el `ImportError`
   siempre se dispara y cae al stub de fallback definido en el propio `ventas.py` (lineas 61-76),
   que retorna literalmente `"Oscuro"` y cuyo `aplicar_tema()` no hace nada
   (`return False`, jamas llama `setStyleSheet`). Busqueda repo-wide de
   `setStyleSheet(TEMAS` no encontro ningun resultado — el diccionario real `config.TEMAS`
   (con claves `"Oscuro"`/`"Claro"`, generado por `modulos/qss_builder.build_themes()`) existe
   pero no se aplica en ningun punto de arranque de la aplicacion. Ver
   `sales_pos_visual_contract.md` para el detalle completo.

Estos 4 hallazgos se mantienen fuera de alcance de POS-1 (que solo documenta y bloquea
estructura) y quedan anotados como trabajo funcional pendiente para una fase SALES-N posterior.

---

## 4. Estados verificados con el widget real

Construidos y capturados via `tests/visual/golden/sales_pos/` contra un `ModuloVentas` real
(no mockeado), con esquema SQLite completo bootstrapeado:

| Estado | Como se produjo | Verificado |
|---|---|---|
| Carrito vacio | Construccion por defecto | `tabla_compra` oculta, `_lbl_cart_empty` visible |
| Carrito con productos | `compra_actual.append(...)` + `actualizar_tabla_compra()` + `calcular_totales()` | `tabla_compra` visible, `_lbl_cart_empty` oculto, fila renderizada |
| Cliente identificado | `cliente_actual = {...}` + `actualizar_info_cliente()` | Fila de display visible, fila de busqueda oculta |
| Carrito + cliente combinados | Ambos anteriores | Ambos efectos simultaneos |
| 1366×768 | `resize(1366, 768)` | Ambos paneles > 0 ancho, derecho ≥ 380px |
| 1920×1080 | `resize(1920, 1080)` | Ancho extra va al panel izquierdo, derecho ≤ 600px |
| QSS "Oscuro" forzado | `app.setStyleSheet(TEMAS["Oscuro"])` | Estructura de 2 paneles se mantiene |
| QSS "Claro" forzado | `app.setStyleSheet(TEMAS["Claro"])` | Estructura de 2 paneles se mantiene |

Estados del master prompt §2 **no cubiertos** en esta fase (requieren mas trabajo de fixture o
no son observables sin hardware real): bascula activa (lectura en vivo), venta suspendida
(el badge "Reanudar (N)"), dialogo de pago abierto. Quedan como pendiente explicito, no
fabricado como "ya probado".
