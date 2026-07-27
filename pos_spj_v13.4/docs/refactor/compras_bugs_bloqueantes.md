# Bugs Bloqueantes — compras_pro.py
_Generado: 2026-05-17 | v13.4 | Fase 0_

## Estado actual de todos los bugs reportados

### Bug 1 — Layout no coincide con diseño solicitado
**Estado**: ⚠️ PARCIALMENTE CORREGIDO

**Root cause original**: Panel de carrito era un widget de 230px fijo en columna derecha;
tabla de items estaba separada del área de totales; columnas no seguían proporción 1:2:1.

**Fixes aplicados** (commit c6ec568):
- `_build_cart_panel()` reemplazó `_build_summary_panel()` con tabla completa
- Columna derecha usa `stretch=2` + `setMinimumWidth(480)` en vez de tamaño fijo
- Sidebar izquierda renombrada a `_build_provider_sidebar()`

**Pendiente para FASE 3**:
- Layout 3 columnas completo con `DocumentToolbar` separado (encabezado proveedor/doc)
- Panel `CapturePanel` (búsqueda + tabla items) en columna central
- `ItemsTotalsPanel` en columna derecha

---

### Bug 2 — Seleccionar proveedor abre ventana inesperada
**Estado**: ✅ CORREGIDO (commit c6ec568)

**Root cause**: `QCompleter` por defecto usa `PopupCompletion` que abre una ventana
flotante de nivel OS. Al hacer click en un item de esa ventana, Qt intentaba hacer
navegación de tab/foco que disparaba código de "abrir detalle".

**Fix aplicado**: `setCompletionMode(QCompleter.InlineCompletion)` — no se abre
ninguna ventana; el completado aparece inline en `txt_proveedor`.
Método canónico `_seleccionar_proveedor(prov_id, nombre)` unifica toda selección.

---

### Bug 3 — `ERROR: no such table: purchase_requests`
**Estado**: ✅ CORREGIDO (migrations 077 + PurchaseRequestUC)

**Root cause**: La tabla nunca existió en BD; el UC tenía el código pero no había
migración que creara las tablas.

**Fixes aplicados**:
- Migración `077_purchase_requests.py` crea las 3 tablas necesarias
- `PurchaseRequestUC._assert_schema()` da error descriptivo si tabla falta
- `PurchaseRequestRepository.schema_ready()` verifica existencia antes de operar

---

### Bug 4 — Búsqueda de producto solo acepta una letra
**Estado**: ✅ CORREGIDO (commit c6ec568)

**Root cause**: `ProductSearchWidget._popup` se construía con `Qt.Tool |
Qt.FramelessWindowHint`, que aunque sin decoraciones sigue siendo una ventana
top-level. En Windows, las ventanas top-level hacen `SetForegroundWindow()` al
mostrarse, robando el foco del campo de texto y haciendo que el siguiente
carácter escrito se pierda.

**Fix aplicado**: Popup cambiado a `QFrame(self.window())` — widget hijo del
main window sin flags de ventana. Los widgets hijos nunca roban el foco a nivel OS.
Posicionamiento cambiado de `mapToGlobal` a `mapTo(win)` + `setGeometry`.

---

### Bug adicional — `no such column: r.peso_total_kg` (recepción QR)
**Estado**: ✅ CORREGIDO (migration 076)

**Root cause**: La columna `peso_total_kg` nunca existió en tabla `recepciones`;
solo existía en `paquetes`. La query en `_cargar_historial_qr()` la referenciaba.

**Fix**: Migración `076_recepciones_peso_total_kg.py` agrega la columna.

---

### Bug adicional — `SyntaxError: invalid decimal literal` en `engine.py`
**Estado**: ✅ CORREGIDO (archivo limpio en repo; solo afectaba copia local Windows)

**Root cause**: Marcadores de conflicto git (`<<<<<<< HEAD` / `>>>>>>>`) quedaron
en la copia local Windows del usuario al hacer merge. El repo siempre estuvo limpio.

**Fix**: Archivo limpio enviado al usuario; comando de reset proporcionado:
```bash
git checkout origin/claude/enterprise-ui-architecture-4ntWv -- pos_spj_v13.4/migrations/engine.py
```

---

## Resumen de estado

| Bug | Descripción | Estado |
|-----|-------------|--------|
| 1 | Layout no coincide con diseño | ⚠️ Parcial (FASE 3 pendiente) |
| 2 | Proveedor abre ventana inesperada | ✅ Corregido |
| 3 | `no such table: purchase_requests` | ✅ Corregido |
| 4 | Búsqueda solo acepta una letra | ✅ Corregido |
| 5 | `no such column: peso_total_kg` | ✅ Corregido |
| 6 | SyntaxError en engine.py | ✅ Corregido |
| — | `_fallback_compra_directa` (código muerto peligroso) | 🔴 Pendiente eliminación |

---

## Bugs que NO existen (verificados)

- ❌ No hay 4ta pestaña para recepción PO separada (son exactamente 3 tabs)
- ❌ No hay widgets ocultos como hack de compatibilidad
- ❌ `_procesar_compra` llama correctamente a `RegistrarCompraUC` como ruta principal
- ❌ No hay PR/PO modificando inventario (PR solo crea registros en `purchase_requests`)
