# Auditoría de Errores — compras_pro.py / spj_product_search.py

Fecha: 2026-05-17  
Rama: claude/enterprise-ui-architecture-4ntWv

---

## Bug 1 — Product Search: no deja escribir más de una letra

**Archivo:** `modulos/spj_product_search.py` línea 85  
**Causa raíz:**  
El popup de resultados se crea con el flag `Qt.Popup`:
```python
self._popup = QFrame(self.window(), Qt.Popup | Qt.FramelessWindowHint)
```
`Qt.Popup` hace que Qt pase el foco de teclado al widget popup en cuanto se muestra.
Después de la primera letra el buscador dispara `_show_popup()`, el popup roba el foco
y el campo de texto deja de recibir keystrokes. El usuario ve que puede escribir una
letra pero no más.

**Corrección:** Cambiar a `Qt.Tool | Qt.FramelessWindowHint` y añadir:
- `WA_ShowWithoutActivating` en el QFrame
- `setFocusPolicy(Qt.NoFocus)` en popup y lista
- `self.txt_search.setFocus()` al final de `_show_popup()`

---

## Bug 2 — Proveedor: no carga datos y abre ventana

**Archivo:** `modulos/compras_pro.py` líneas 746-750  
**Causa raíz — doble problema:**

1. **No se conecta `QCompleter.activated[str]`.**  
   La única conexión es `editingFinished → _resolver_proveedor_desde_texto`.
   El QCompleter muestra su dropdown (que Qt renderiza como una ventana flotante
   separada del proceso de foco normal). Cuando el usuario hace clic en un ítem,
   `activated[str]` se dispara pero nadie lo escucha. `editingFinished` puede o no
   dispararse dependiendo del flujo de foco, por lo que la carga de datos (RFC,
   tel, crédito) queda sin ejecutar.

2. **La "ventana" que se abre ES el popup del QCompleter.**  
   Qt5 por defecto muestra las sugerencias del QCompleter como un `QListView`
   flotante que el sistema operativo trata como ventana independiente. Eso es lo
   que el usuario percibe como "abre una ventana".

3. **No existe un punto canónico para seleccionar proveedor.**  
   La lógica de carga de datos está duplicada en `_resolver_proveedor_desde_texto`
   y `_seleccionar_proveedor_sidebar`. Cualquier cambio futuro se debe hacer en dos
   lugares.

**Corrección:**
- Crear método canónico `_seleccionar_proveedor(prov_id, nombre)` que hace TODO
  (guarda id, pone texto, carga RFC/tel/dirección/crédito/alertas, actualiza validación)
- Conectar `_prov_completer.activated[str]` a `_on_completer_activated(nombre)` que
  busca el id y llama `_seleccionar_proveedor`
- `_seleccionar_proveedor_sidebar` → delega a `_seleccionar_proveedor`
- `_resolver_proveedor_desde_texto` → delega a `_seleccionar_proveedor` en match

---

## Bug 3 — ERROR no such table: purchase_requests

**Archivo:** `application/purchases/purchase_request_uc.py` (NO EXISTE)  
**Logger:** `spj.purchases.pr_uc` — método `crear_pr`  
**Causa raíz:**  
La tabla `purchase_requests` (y sus tablas relacionadas `purchase_request_items`,
`purchase_request_events`) nunca fueron creadas por ninguna migración. El UC que
las usa existe en el entorno del cliente pero no tiene su migración de esquema.

Búsqueda exhaustiva: 0 referencias en los 550 archivos .py del repo.

**Corrección:**
- Migración 077 crea las 3 tablas (idempotente, no destructiva)
- UC creado con guardia de tabla al inicio: si la tabla no existe → error con mensaje
  claro, no stacktrace
- Registrar en `engine.py`

---

## Bug 4 — UI layout: tabla en columna incorrecta

**Archivo:** `modulos/compras_pro.py` método `_build_tab_tradicional` líneas 824-916  
**Causa raíz:**  
La tabla de partidas (`self.tabla`, `self._grp_cart`) se construye en la columna
CENTRAL, que tiene `stretch=1`. La columna derecha (`_build_summary_panel`) es
`setFixedWidth(230)` — demasiado angosta para una tabla. El resultado es que la
tabla queda comprimida en el centro y el panel derecho muestra sólo un resumen
numérico estrecho.

El layout solicitado coloca la tabla en la columna DERECHA junto a totales, pago
y acciones, con la columna central reservada para el formulario del proveedor y la
búsqueda de productos.

**Corrección:**
- Mover `self._grp_cart` + footer IVA de `center_lay` → nuevo `_build_cart_panel()`
- `_build_cart_panel()` reemplaza `_build_summary_panel()` con:
  - Panel ancho (stretch=2, min 480px) en vez de fijo 230px
  - Cart table arriba (stretch)
  - Footer IVA debajo de tabla
  - Resumen financiero compacto
  - Pago + Autorizar al fondo
- Columna central queda: Stepper + Documento + Buscador + CxP alert (más limpia)

---

## Riesgos residuales

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| QCompleter popup sigue siendo "ventana" del SO | Baja — es comportamiento nativo Qt | No configurable sin reimplementar QCompleter |
| Tabla muy larga en resoluciones pequeñas (< 1280px) | Media | Tabla tiene scroll vertical; min-width en panel |
| `purchase_request_uc.py` necesitará lógica de negocio completa | Alta | UC creado con stub; error descriptivo si tabla falta |
