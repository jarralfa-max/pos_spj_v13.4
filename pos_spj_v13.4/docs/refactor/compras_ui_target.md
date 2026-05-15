# UI Target — Módulo Compras (Fase 8+)
> Basado en referencia visual PROMPT MAESTRO CODEX | 2026-05-15

---

## Tab 1 — Compra Tradicional: Layout Objetivo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  KPI Strip: Compras mes | Órdenes abiertas | CXP pendiente | Proveedores    │
├──────────────────┬──────────────────────────┬───────────────────────────────┤
│ COLUMNA IZQ      │ COLUMNA CENTRAL          │ COLUMNA DERECHA               │
│ Toolbar          │ Captura Documental       │ Partidas + Totales            │
│ Documental ERP   │                          │                               │
│                  │ Datos Proveedor:         │ Grid: SKU | Prod | Cant | UM  │
│ [📋 PR pend.  2] │  • proveedor dropdown    │       | Costo | Desc | IVA   │
│ [✅ PR aprobad ] │  • RFC, tel, dirección   │       | Subtotal | Acciones  │
│ [📦 PO abiertas] │  • condición pago        │                               │
│ [🔄 Rec. parc. ] │  • crédito disponible    │ Footer:                       │
│ [📜 Hist. rápido]│                          │  Subtotal / Desc / IVA       │
│                  │ Datos Documento:         │  Flete / Total               │
│ ─── Detalle ─── │  • factura/remisión      │  Método / Forma / Plazo      │
│                  │  • fecha                 │                               │
│ Folio: PR-068124 │  • sucursal destino      │ Botón dinámico:              │
│ Estado: PENDIENTE│  • tipo doc              │  [Guardar borrador]           │
│ Fecha: 05/05     │  • moneda, prioridad     │  [Generar PR]                 │
│ Proveedor: Carnes│  • solicitante, notas    │  [Aprobar PR]                 │
│ Monto: $12,440   │                          │  [Convertir a PO]             │
│ Prioridad: ALTA  │ Búsqueda Producto:       │  [Enviar a Recepción]         │
│                  │  • barcode/SKU/nombre    │  [Procesar compra]            │
│ Acciones:        │  • báscula si disponible │                               │
│ [✓ APROBAR PR]   │  • [+ ADD]               │                               │
│ [✗ RECHAZAR]     │                          │                               │
│ [✏ EDITAR]       │ Doctype Toolbar (F5):    │                               │
│ [→ CONV. A PO]   │  [DIRECT] [PR] [PO]      │                               │
│ [↗ ENVIAR A REC] │                          │                               │
└──────────────────┴──────────────────────────┴───────────────────────────────┘
```

---

## Columna Izquierda — Toolbar Documental ERP (FASE 8)

### Listas documentales
```
PR pendientes       badge(count)
PR aprobadas        badge(count)
PO abiertas         badge(count)
Recepciones parciales badge(count)
Historial rápido
```

### Panel de detalle al seleccionar documento
```
Folio:         PR-068124
Estado:        [PENDIENTE] badge
Fecha:         05/05/2026
Sucursal:      Sucursal Centro
Solicitante:   Juan Pérez (Dpto. Carnes)
Proveedor:     Carnes del Norte S.A.
Monto:         $12,440
Prioridad:     ALTA badge
Tipo:          Solicitud PR
Vencimiento:   16/06/2026
```

### Botones de acción (habilitados/disabled según estado + permiso)
```
[✓ APROBAR PR]    → PRState: PENDIENTE_APROBACION, perm: purchases.pr.approve
[✗ RECHAZAR]      → mismo estado, perm: purchases.pr.reject
[✏ EDITAR]        → estado: BORRADOR, perm: purchases.pr.edit
[→ CONV. A PO]    → estado: APROBADA, perm: purchases.po.create
[↗ ENVIAR A REC.] → PO estado: ABIERTA|PARCIAL, perm: purchases.po.send_to_receipt
```

### Comportamiento
- Clic en item carga el documento completo en columna central + derecha
- Sin abrir ventanas modales para operaciones básicas
- Reload automático tras acción (aprobar/rechazar/convertir)
- Badges usan Colors.WARNING_BASE (pendiente), Colors.SUCCESS_BASE (aprobada), Colors.PRIMARY_BASE (PO)

---

## Columna Central — Captura Documental

### Datos Proveedor (ya existe en compras_pro.py)
- Combo proveedor + botón reasignar
- RFC, teléfono, dirección, condición pago, crédito disponible
- Label status proveedor (crédito OK / sin crédito)

### Datos Documento (ya existe parcialmente)
- Factura/remisión (doc_ref)
- Fecha documento
- Sucursal destino
- Tipo documento (ya: _build_doctype_toolbar, Fase 5)
- Moneda + prioridad
- Notas, solicitante

### Búsqueda Producto (ya existe)
- Barcode scan / SKU / nombre
- Botón + ADD
- Import desde plantilla

---

## Columna Derecha — Partidas + Totales

### Grid (ya existe: _tbl_compra_items)
Columnas sugeridas para Fase 8 review:
```
SKU | Producto | Cant | UM | Peso est. | Costo | Desc | IVA | Subtotal | Acc.
```

### Footer (ya existe parcialmente)
```
Subtotal:    $XXX
Descuento:   -$XX
IVA:         $XX
Total:       $XXX
Método:      CRÉDITO 30 días
Vence:       05/06/2026
```

### Botón Dinámico
Estado actual del botón según `_doc_type` + estado + permisos:

| Condición | Texto botón | Acción |
|-----------|------------|--------|
| doc_type=DIRECT | ✓ Autorizar compra | _procesar_compra → DIRECT |
| doc_type=PR, estado=nuevo | 📋 Crear solicitud | _procesar_compra → PR |
| doc_type=PR, cargada, estado=BORRADOR | 📋 Enviar a aprobación | submit_pr |
| doc_type=PR, estado=APROBADA | → Convertir a PO | convertir_a_po |
| doc_type=PO, estado=ABIERTA | ↗ Enviar a recepción | send_to_receipt |

---

## Tab 2 — Recepción QR (Fase 9)

Solo UI/UX. Etapas visuales:
1. Identificar contenedor (ya existe)
2. Asignar compra / PO (ya existe, Fase 6 agrega PO)
3. Recibir físico (ya existe)

Mostrar al recibir desde PO:
- Líneas esperadas vs recibidas
- Estado de la PO (PARCIAL/RECIBIDA)
- Diferencias y mermas

---

## Tab 3 — Histórico (ya implementado Fase 7)

- 9 columnas en _tbl_hist ✅
- Filtro tipo_doc (directa / con PO) ✅
- Timeline documental _hist_timeline_bar ✅
- Badges Tipo Doc (col 7) ✅

Pendiente (Fase 10):
- Exportar CSV (si no existe)
- Filtro por estado de PO
- Documentos/evidencias adjuntos

---

## Sistema de Estilos para Fase 8

```python
# CORRECTO: usar tokens
from modulos.design_tokens import Colors
badge.setStyleSheet(
    f"background:{Colors.WARNING_BASE}22;"
    f"color:{Colors.WARNING_BASE};"
    f"border:1px solid {Colors.WARNING_BASE}60;"
)

# CORRECTO: usar apply_spj_buttons
from modulos.spj_styles import apply_spj_buttons
apply_spj_buttons(self)  # auto-estila todos los QPushButton

# INCORRECTO: hex hardcodeado
badge.setStyleSheet("background:#ff9900;color:#fff;")  # ❌
```

### Badges de estado PR
```python
_PR_BADGE_STYLES = {
    "BORRADOR":             (Colors.NEUTRAL.SLATE_500, Colors.NEUTRAL.SLATE_100),
    "PENDIENTE_APROBACION": (Colors.WARNING_BASE,     Colors.WARNING_BASE),
    "APROBADA":             (Colors.SUCCESS_BASE,     Colors.SUCCESS_BASE),
    "RECHAZADA":            (Colors.DANGER_BASE,      Colors.DANGER_BASE),
    "CONVERTIDA_A_PO":      (Colors.PRIMARY_BASE,     Colors.PRIMARY_BASE),
    "CANCELADA":            (Colors.NEUTRAL.SLATE_400, Colors.NEUTRAL.SLATE_200),
}
```
