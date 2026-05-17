# ERROR: Tab PO Reception en posición incorrecta
> Generado: 2026-05-17 | Relacionado con: PROMPT MAESTRO ESTRICTO §4

---

## Descripción del problema (histórico)

En versiones anteriores del módulo existía (o se intentó agregar) un 4° tab externo en `ModuloComprasPro` para "Recepción PO", en el mismo nivel que:
- Tab 0: Compra Tradicional
- Tab 1: Recepción con QR
- Tab 2: Historial de Compras
- ~~Tab 3: Recepción PO~~ ← INCORRECTO — generó regresión

---

## Estado actual (correcto)

```
ModuloComprasPro._build_ui() — 3 tabs externas ÚNICAMENTE:
  Tab 0: "🛒 Compra Tradicional"   (compras_pro.py L722)
  Tab 1: "📦 Recepción con QR"     (compras_pro.py L726)
  Tab 2: "📋 Historial de Compras" (compras_pro.py L730)

RecepcionQRWidget._build_ui() — 5 tabs internas:
  Tab 0: "🏷️ 1. Generar Etiqueta QR"  (recepcion_qr_widget.py L98)
  Tab 1: "📋 2. Asignar Compra"        (recepcion_qr_widget.py L99)
  Tab 2: "📦 3. Recepcionar"           (recepcion_qr_widget.py L100)
  Tab 3: "📜 Historial"                (recepcion_qr_widget.py L101)
  Tab 4: "🧾 Recepción PO"             (recepcion_qr_widget.py L102) ← CORRECTO aquí
```

**La Recepción PO VIVE DENTRO del widget QR como sub-pestaña interna.**

---

## Decisión de arquitectura

### ¿Por qué PO reception está dentro del widget QR?

1. **Flujo de usuario:** La recepción física de mercancía (QR o PO) sucede en el almacén. Agrupar las dos modalidades de recepción física en un mismo tab ("Recepción con QR") mantiene coherencia UX.

2. **Separación de responsabilidades:** El módulo externo `ModuloComprasPro` gestiona el ciclo documental (crear compra, solicitud, orden). La recepción física es una etapa posterior que pertenece al tab de recepción.

3. **No duplicar lógica:** Si existiera un tab externo de "Recepción PO" y también el tab interno en QR, habría dos puntos de entrada para la misma operación → doble inventario.

---

## Regla inviolable

> **Solo 3 tabs en el nivel externo de ModuloComprasPro.**  
> Cualquier adición de un 4° tab de tipo "recepción" o "PO" en el nivel externo es un ERROR de arquitectura y debe revertirse inmediatamente.

---

## Test de regresión

```python
# tests/purchases/test_qr_no_extra_po_tab.py
def test_outer_tabs_count_is_exactly_3():
    """ModuloComprasPro must have exactly 3 top-level tabs."""
    ...

def test_no_fourth_po_tab_in_outer_module():
    """No 'PO' or 'Recepción PO' tab must exist at outer level."""
    ...

def test_po_reception_tab_is_inside_qr_widget():
    """_tab_po_recv must exist inside RecepcionQRWidget, not in outer module."""
    ...
```

---

## Verificación de código actual

```bash
# Verificar que no haya 4° tab externo:
grep -n "addTab" pos_spj_v13.4/modulos/compras_pro.py
# Debe mostrar EXACTAMENTE 3 líneas con addTab en _build_ui()

# Verificar que el tab PO está en el lugar correcto:
grep -n "addTab.*PO\|po_recv\|Recepci.*PO" pos_spj_v13.4/modulos/recepcion_qr_widget.py
# Debe mostrar UNA línea: "🧾 Recepción PO" en recepcion_qr_widget.py
```

---

## Resultado de verificación (2026-05-17)

```
compras_pro.py addTab lines:
  L722: self._tabs.addTab(tab_trad, "🛒 Compra Tradicional")
  L726: self._tabs.addTab(tab_qr,   "📦 Recepción con QR")
  L730: self._tabs.addTab(tab_hist, "📋 Historial de Compras")
  TOTAL: 3 tabs ✅

recepcion_qr_widget.py PO tab:
  L102: self._tabs.addTab(self._tab_po_recv, "🧾 Recepción PO")
  TOTAL: 1 (en lugar correcto) ✅
```

**CONCLUSIÓN: No existe el error actualmente. El test de regresión previene su reaparición.**
