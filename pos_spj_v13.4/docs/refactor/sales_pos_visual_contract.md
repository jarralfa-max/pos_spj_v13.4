# Sales/POS — Contrato visual (SALES-1 / POS-1)

Fecha: 2026-08-16
Complementa: `sales_pos_layout_inventory.md` (arbol de widgets + medidas exactas),
`tests/visual/golden/sales_pos/` (18 tests que hacen cumplir este contrato contra el
widget real), `SALES-0_auditoria.md` (auditoria de codigo de negocio, no visual).

> Regla Visual No Negociable (master prompt §1): el layout actual de la ventana de
> Ventas/POS debe conservarse. Este documento fija que significa eso en terminos
> verificables — que se puede tocar y que no — para que las siguientes fases de SALES-N
> (dominio, permisos, hardware, pagos, ...) puedan reescribir la arquitectura interna sin
> arriesgar el layout.

---

## 1. Jerarquia (obligatoria, verificada contra el widget real)

```text
VENTAS / POS
├── Barra superior (posCashierBar, 48px fijo)
│   Título · Cajero(meta) · [stretch] · Estado · Báscula · Terminal · Corte Z
├── Cuerpo (QSplitter horizontal, 2 paneles, sizes iniciales [620, 460])
│   ├── Panel izquierdo — Catálogo (stretch factor 1)
│   │   Búsqueda+scanner → Categorías+vista → Grid de productos
│   └── Panel derecho — Checkout (stretch factor 0, ancho 380-600px)
│       Carrito → Cliente → Totales → Descuentos rápidos →
│       Cobrar → Suspender/Reanudar/Cancelar → Devolución/Factura/Reimpr.
```

Esta jerarquia esta protegida por `tests/visual/golden/sales_pos/
test_pos_preserves_two_panel_layout.py` (exactamente 1 splitter, exactamente 2 paneles) y
`test_pos_cashier_bar_position.py` (barra superior siempre primera, siempre 48px).

**Nota de orden real vs. lista del master prompt**: dentro del panel derecho, el carrito se
renderiza ANTES que la seccion de cliente (ver `sales_pos_layout_inventory.md` §1 nota) — el
orden de bullets de la seccion 1 del master prompt es una lista de contenido, no una secuencia
vertical exacta obligatoria. El contrato de ESTE documento protege el orden real
(`carrito → cliente → totales → descuentos → cobrar → secundarios → utilidad`), verificado por
`test_pos_customer_panel_position.py` y `test_pos_checkout_actions_position.py`.

---

## 2. Zonas que NO pueden cambiar (bloqueadas por tests)

| Regla | Test que la protege |
|---|---|
| Un solo `QSplitter`, exactamente 2 paneles | `test_pos_preserves_two_panel_layout.py` |
| Barra de cajero es el primer widget, 48px, arriba del cuerpo | `test_pos_cashier_bar_position.py` |
| Catálogo es el panel IZQUIERDO del splitter | `test_pos_catalog_panel_remains_left.py` |
| Checkout es el panel DERECHO, ancho acotado [380, 600]px | `test_pos_checkout_panel_remains_right.py` |
| Cliente se renderiza debajo del carrito (orden real) | `test_pos_customer_panel_position.py` |
| Carrito absorbe el espacio vertical flexible (`Expanding`, minH 160) | `test_pos_cart_position.py` |
| Totales visibles, entre cliente y las acciones de checkout | `test_pos_totals_position.py` |
| Orden: barra de descuentos → bloque Cobrar → barra de utilidad | `test_pos_checkout_actions_position.py` |
| Cobrar es la accion dominante (minH 48, `class=success`, `fill_parent`) | `test_pos_primary_charge_button_is_dominant.py` |
| Badges F6-F12 presentes y en el boton correcto | `test_pos_shortcut_buttons_are_visible.py` |
| Estructura se mantiene en 1366×768 y 1920×1080 | `test_pos_layout_at_1366x768.py` / `_1920x1080.py` |
| Estructura se mantiene con QSS "Oscuro"/"Claro" aplicado | `test_pos_dark_theme_layout.py` / `_light_theme_layout.py` |
| Estados carrito-vacio / con-items / cliente-identificado no rompen estructura | `test_pos_layout_matches_golden_master.py` |

Cualquier cambio que rompa uno de estos 18 tests es, por definicion, el tipo de "cambio
estructural" que POS-1 existe para bloquear (master prompt §1, "no se permite").

## 3. Zonas que SI pueden cambiar (permitido por el master prompt §1)

- Limpieza interna de codigo, division de `modulos/ventas.py` en componentes mas pequenos
  (siempre que el arbol de widgets resultante siga pasando los 18 tests de arriba).
- Migrar los widgets internos al Design System (`PageHeader`/`StandardDialog`/etc. — master
  prompt §57) siempre que las proporciones/orden documentados aqui no cambien.
- Cablear datos reales donde hoy hay placeholders/decoracion (ver §4 — esto es exactamente lo
  que las fases siguientes de SALES-N deben hacer, sin tocar el layout que los contiene).
- Accesibilidad, tooltips, feedback visual, estados vacios, rendimiento.

---

## 4. Hallazgos honestos: lo que el layout MUESTRA vs. lo que HACE hoy

POS-1 es solo de documentacion/bloqueo estructural — ninguno de estos se corrigio en esta
fase. Se listan aqui para que ninguna fase futura asuma que ya funcionan.

### 4.1 Atajos F6-F12

**No estan cableados.** `modulos/ventas.py::keyPressEvent` (linea 2394) solo maneja el buffer
de scanner HID y las teclas Enter/Tab; no contiene ninguna rama para `Qt.Key_F6`..`Qt.Key_F12`.
Busqueda repo-wide de `Key_F(6|7|8|9|10|11|12)` no encontro ningun `QShortcut` en
`interfaz/`, `core/`, ni en ningun otro modulo. Los badges "F6".."F12" pintados por
`_FKeyButton.paintEvent` (linea 126) son puramente decorativos hoy. **Implicacion para
SALES-N**: cablear atajos reales es trabajo funcional nuevo, no una regresion a arreglar — el
master prompt §54 ("Los atajos deben registrarse canonicamente") describe el estado
DESEADO, no el actual.

### 4.2 Tema claro/oscuro

**No esta cableado en produccion.** `modulos/ventas.py` (lineas 55-77) intenta
`from config import TEMAS, configuraciones_POR_DEFECTO, GestorTemas`, pero `config.py`
(verificado, archivo completo de 36 lineas) solo define `TEMAS` y `BASE_DIR`/`ICONS_DIR`/
`DATABASE_NAME` — no define `GestorTemas` ni `configuraciones_POR_DEFECTO`. El
`ImportError` resultante SIEMPRE se dispara, cayendo al stub de fallback local que:
- `obtener_tema_actual()` → retorna literalmente `"Oscuro"` sin consultar nada.
- `aplicar_tema(widget, nombre_tema)` → `return False`, nunca llama `setStyleSheet`.

Busqueda repo-wide de `setStyleSheet(TEMAS` (el patron que aplicaria el QSS real
generado por `modulos/qss_builder.build_themes()`) no arrojo ningun resultado en todo el
repositorio — ni en `main.py`, ni en `interfaz/main_window.py`, ni en ningun otro archivo.
El diccionario real `config.TEMAS = {"Oscuro": "...", "Claro": "..."}` existe como activo
(usado por los tests de esta fase directamente), pero **ningun camino de ejecucion real de la
aplicacion lo aplica hoy**. La apariencia visual real de la app en produccion no viene de este
mecanismo. **Implicacion para SALES-N/otras fases**: activar el tema real es trabajo de
wiring nuevo (ademas, fuera del bounded context de Sales — probablemente pertenece a un
futuro "Theme" cross-cutting), no algo que romper.

### 4.3 Boton "Terminal" en la barra de cajero

Etiquetado "💳 Terminal", pero su texto en tiempo de ejecucion se sobrescribe con el
**nombre de sucursal** (`set_sucursal`/`on_branches_changed`, ~lineas 1326-1331 y
1372-1373) — no refleja estado de hardware. No existe integracion de terminal de pago en
ningun punto del repositorio (confirmado en `SALES-0_auditoria.md` §7/Matriz de
capabilities). El boton en si (posicion, tamano) SI esta protegido por este contrato; su
contenido/binding no.

### 4.4 Badge de estado "● Abierto"

Texto estatico fijado una sola vez en `init_ui` (linea 1470); no hay ninguna otra asignacion
`.setText` sobre `_lbl_status_badge` en todo el archivo. No refleja
`finance_service.get_estado_turno()` en tiempo real, a pesar de que esa validacion SI se
ejecuta (de forma separada, bloqueante) en `procesar_pago` (ver `SALES-0_auditoria.md`).

---

## 5. Como leer las capturas de este contrato

Las capturas PNG generadas por `tests/visual/golden/sales_pos/` (via la variable de entorno
`SALES_POS_VISUAL_ARTIFACTS`) se renderizan con `QT_QPA_PLATFORM=offscreen`, el mismo enfoque
ya usado por `tests/ui/test_purchasing_visual_closure.py`. En este entorno headless las
fuentes/emoji no siempre tienen glifos disponibles — las capturas muestran la geometria y
estructura real (posicion/tamano de cada bloque) pero NO deben leerse como prueba de
apariencia tipografica pixel-perfect. Las aserciones de geometria (tamanos, posiciones
relativas, visibilidad) son la garantia real de regresion, no la imagen en si — exactamente
la misma disciplina que el precedente de Purchasing ya establecio en este repositorio.

Para ver el layout real con fuentes/tema, se requiere ejecutar la aplicacion completa en un
entorno con pantalla (Windows real) — no verificado en esta fase por ser un audit/POS-1
ejecutado en modo automatizado; queda como pendiente si se requiere evidencia visual con
render completo.
