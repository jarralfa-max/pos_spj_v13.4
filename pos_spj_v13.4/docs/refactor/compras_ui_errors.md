# INVENTARIO DE ERRORES UI — Módulo Compras Pro
> Generado: 2026-05-17 | Severidades: CRÍTICO / ALTO / MEDIO / BAJO

---

## Errores UI activos (confirmados)

### ERROR-UI-01 — Colores hardcodeados SLATE_50 como fondo de widget principal
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py`  
**Líneas:** 2354, 4196, 4363  
**Descripción:** Se usa `Colors.NEUTRAL.SLATE_50` como fondo de QFrame en zonas principales del panel de totales y del historial. En tema Dark, SLATE_50 es un gris claro que rompe el contraste.  
**Impacto:** UI visual — panel se ve blanco/claro en tema oscuro.  
**Regla violada:** "NO usar Colors.NEUTRAL.SLATE_50 como fondo fijo en widgets de Compra Tradicional"  
**Fix:** Usar `background:transparent` o `palette().window()` para heredar del tema.

### ERROR-UI-02 — background:white hardcodeado en QLineEdit del panel de proveedor
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py`  
**Línea:** 2381  
**Descripción:** `"background:white;font-size:11px;outline:none;"` en un QLineEdit de la sección de información del proveedor.  
**Impacto:** En tema Dark el input aparece blanco con texto blanco (invisible).  
**Regla violada:** "NO usar background:white"  
**Fix:** Remover `background:white` del estilo inline; usar `QLineEdit { background: palette(base); }` en QSS global o dejar sin background para que lo aplique el tema.

### ERROR-UI-03 — background:white en Colors.NEUTRAL.WHITE en tabla historial
**Severidad:** BAJO  
**Archivo:** `compras_pro.py`  
**Línea:** 4979  
**Descripción:** `Colors.NEUTRAL.WHITE` en alternado de filas del historial. Este color es #ffffff hardcodeado.  
**Impacto:** Alternado de filas visualmente roto en tema oscuro.  
**Regla violada:** "NO usar background:white"  
**Fix:** Usar alpha transparente sobre color base del tema, o eliminar alternado y dejar QSS global de QTableWidget.

### ERROR-UI-04 — Stepper bar visible en modo DIRECT
**Severidad:** ALTO  
**Archivo:** `compras_pro.py`  
**Líneas:** 2741-2778 (`_refresh_stepper`)  
**Descripción:** `_refresh_stepper()` intenta actualizar el stepper de documentos. El stepper se construye y se almacena como `self._hidden_stepper` pero su lógica de refresco puede exponer el widget cuando `_doc_type == "DIRECT"`.  
**Impacto:** Stepper visible cuando no debe. Confunde al usuario en flujo directo.  
**Fix:** Guardar `_refresh_stepper` con guard explícito: `if self._doc_type == "DIRECT": return`.

### ERROR-UI-05 — Panel proveedor SLATE_50 background
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py`  
**Línea:** 2354  
**Descripción:** `_build_provider_sidebar()` (L2349) crea el panel con `background:{Colors.NEUTRAL.SLATE_50}`.  
**Impacto:** En dark mode el sidebar del proveedor tiene fondo claro.  
**Fix:** Cambiar a `background:transparent` o eliminar el background del frame.

### ERROR-UI-06 — Doble instanciación del widget `_build_provider_sidebar`
**Severidad:** ALTO  
**Archivo:** `compras_pro.py`  
**Líneas:** 900 (`_build_provider_card`) y 2349 (`_build_provider_sidebar`)  
**Descripción:** Existen dos métodos que construyen UI de proveedor: `_build_provider_card()` (integrado en columna central, visible) y `_build_provider_sidebar()` (construido pero posiblemente nunca agregado al layout visible).  
**Impacto:** Duplicación de widgets; el segundo puede ser desperdicio de memoria o estar causando confusión en `_cargar_info_proveedor`.  
**Fix:** Auditar si `_build_provider_sidebar()` sigue siendo llamado. Si no, marcar como dead code a eliminar en Fase 4.

### ERROR-UI-07 — apply_spj_buttons() rompe botones custom con inline style
**Severidad:** BAJO  
**Archivo:** `modulos/spj_styles.py` (L132-146)  
**Descripción:** `apply_spj_buttons()` salta botones que ya tienen `border-radius:5px` y `font-weight:bold`, pero puede sobrescribir botones que tenían estilos inline con variante correcta pero sin esas marcas exactas.  
**Impacto:** Algunos botones de iconos pequeños (< 36px) pierden su estilo custom.  
**Fix ya aplicado:** `btn.minimumWidth() <= 36 or btn.minimumWidth() == btn.maximumWidth() == 30`  
**Estado:** RESUELTO en commit `2763428`.

### ERROR-UI-08 — KPI bar no refresca en cambio de tab
**Severidad:** MEDIO  
**Archivo:** `compras_pro.py`  
**Líneas:** 839-899 (`_build_purchase_kpi_bar`), 4047 (`_on_tab_change`)  
**Descripción:** Los KPI cards se construyen una vez y el método `_refresh_kpi_cards()` (L881) se llama desde `__init__` con delay, pero no cuando el usuario regresa a la tab "Compra Tradicional".  
**Impacto:** KPIs muestran datos desactualizados si el usuario hizo una compra en otra pestaña.  
**Fix:** En `_on_tab_change(idx)`, cuando `idx == 0`, llamar `QTimer.singleShot(0, self._refresh_kpi_cards)`.

### ERROR-UI-09 — QSplitter sin handle visual adecuado
**Severidad:** BAJO  
**Archivo:** `compras_pro.py`  
**Línea:** 815  
**Descripción:** El handle del QSplitter usa `rgba(0,0,0,0.08)` que en tema Dark es invisible.  
**Impacto:** El usuario no ve el separador de columnas.  
**Fix:** Usar color fijo de tokens o `rgba(128,128,128,0.3)`.

---

## Errores UI resueltos (histórico)

### ERROR-UI-R01 — fixedSize() en apply_spj_buttons (AttributeError)
**Resuelto:** Commit `2763428`  
**Descripción:** `QPushButton` no tiene `.fixedSize()`. Causaba `AttributeError` al cargar el módulo.

### ERROR-UI-R02 — C++ deleted object en _refresh_stepper
**Resuelto:** Commit `2763428`  
**Descripción:** `self._build_stepper_bar().hide()` — sin guardar referencia, Python GC destruía el objeto C++.

### ERROR-UI-R03 — KPI bar duplicada dentro del tab y fuera
**Resuelto:** Sesión anterior  
**Descripción:** `_build_purchase_kpi_bar()` era llamada tanto en `_build_ui()` como dentro de `_build_tab_tradicional()`.

### ERROR-UI-R04 — QSplitter colapsaba columna derecha
**Resuelto:** Sesión anterior  
**Descripción:** `setSizes([260, 9999, 480])` colapsaba la columna derecha. Fix: `setSizes([260, 500, 440])` con `setStretchFactor(1, 1)`.

---

## Errores de accesibilidad

### ERROR-ACC-01 — Tooltips ausentes en botones de acción
**Severidad:** BAJO  
**Descripción:** Los botones `_btn_procesar`, `_btn_borrador`, `_btn_enviar` no tienen tooltips obligatorios.  
**Fix:** `apply_spj_tooltips(self)` en `_build_ui()` (ya está en el plan de Fase 1).

### ERROR-ACC-02 — Labels sin texto accesible en KPI cards
**Severidad:** BAJO  
**Descripción:** Los `_PurchaseKPICard` no tienen `setAccessibleName`.  
**Fix:** Fase posterior.
