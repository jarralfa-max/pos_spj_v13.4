# Arquitectura Documental Objetivo — Módulo Compras
> Versión: 2026-05-15

---

## Capas de la Arquitectura Documental

```
┌─────────────────────────────────────────────────────────────┐
│  UI — modulos/compras_pro.py                                │
│  ModuloComprasPro (QWidget)                                 │
│  ├── Tab 1: Compra Tradicional                              │
│  │   ├── Columna izquierda: Toolbar Documental ERP (Fase 8) │
│  │   ├── Columna central: Captura Documental                │
│  │   └── Columna derecha: Partidas + Totales + Botón dyn.   │
│  ├── Tab 2: QR / Recepción (QR NO-TOUCH)                    │
│  └── Tab 3: Historial (Fase 7 ✅)                           │
└──────────────────────────────────┬──────────────────────────┘
                                   │ llama use cases
┌──────────────────────────────────▼──────────────────────────┐
│  Application — application/purchases/                       │
│  TraditionalPurchaseUC   → router DIRECT/PR/PO              │
│  PurchaseRequestUC       → PR CRUD + estados                │
│  PurchaseOrderUC         → PO CRUD + estados                │
│  ReceivePOAdapter        → PO physical receipt              │
│  RegistrarCompraUC       → compra DIRECT (canónico)         │
└──────────────────────────────────┬──────────────────────────┘
                                   │ delega a
┌──────────────────────────────────▼──────────────────────────┐
│  Core Services                                              │
│  PurchaseService         → register_purchase (SAVEPOINT)    │
│  InventoryService        → add_stock → kardex               │
│  FinanceService          → crear_cxp + registrar_asiento    │
│  LoteService             → registrar_lote                   │
│  AuditService            → audit_write                      │
│  EventBus                → PURCHASE_ITEMS_PROCESS           │
│                            COMPRA_REGISTRADA                │
└──────────────────────────────────┬──────────────────────────┘
                                   │ persiste en
┌──────────────────────────────────▼──────────────────────────┐
│  Repositories                                               │
│  PurchaseRepository      → compras + detalles_compra        │
│  PurchaseOrderRepository → ordenes_compra + items           │
│  PurchaseRequestRepository → purchase_requests + items      │
└─────────────────────────────────────────────────────────────┘
```

---

## Modelo Documental Implementado

### Tablas Nuevas (Fases 3-4)

```sql
-- Fase 3 (migración 076)
CREATE TABLE purchase_requests (
    id INTEGER PRIMARY KEY,
    folio TEXT UNIQUE,
    estado TEXT DEFAULT 'BORRADOR',
    -- BORRADOR | PENDIENTE_APROBACION | APROBADA | RECHAZADA | CONVERTIDA_A_PO | CANCELADA
    proveedor_id INTEGER, proveedor_nombre TEXT,
    sucursal_id INTEGER, usuario TEXT,
    subtotal REAL, iva_monto REAL, total REAL,
    metodo_pago TEXT, condicion_pago TEXT, plazo_dias INTEGER, moneda TEXT,
    notas TEXT, doc_ref TEXT,
    aprobado_por TEXT, rechazado_por TEXT, motivo_rechazo TEXT, fecha_aprobacion DATETIME,
    fecha_creacion DATETIME, fecha_actualizacion DATETIME
);

CREATE TABLE purchase_request_items (
    id INTEGER PRIMARY KEY,
    pr_id INTEGER REFERENCES purchase_requests(id),
    producto_id INTEGER, nombre TEXT,
    cantidad REAL, unidad TEXT, precio_unitario REAL,
    descuento REAL, subtotal REAL, lote TEXT, fecha_caducidad DATE, notas TEXT
);

-- Fase 4 (migración 077 — extensión ordenes_compra)
-- Añade: pr_id, sucursal_id, aprobado_por, metodo_pago, subtotal, iva_monto, etc.

-- Fase 4 (migración 078)
-- Añade: compras.purchase_order_id FK → ordenes_compra
```

### Columnas Faltantes (Deuda para Fases futuras)

| Tabla | Columna faltante | Migración sugerida | Impacto |
|-------|-----------------|-------------------|---------|
| `compras` | `document_type` TEXT DEFAULT 'DIRECT' | 079 | Trazabilidad tipo compra |
| `compras` | `pr_id` INTEGER | 080 | Link PR→compra directa |
| `compras` | `approved_by` TEXT | 080 | Auditoría aprobación |
| `recepciones` | `purchase_order_id` INTEGER | 081 | Trazabilidad PO→recepción |

---

## Máquina de Estados (Implementada en states.py)

```python
# PRState — application/purchases/states.py
BORRADOR → PENDIENTE_APROBACION → APROBADA → CONVERTIDA_A_PO
PENDIENTE_APROBACION → RECHAZADA
BORRADOR | PENDIENTE_APROBACION → CANCELADA

# POState
ABIERTA → PARCIAL → RECIBIDA → CERRADA
ABIERTA | PARCIAL → CANCELADA

# DirectPurchaseState (legacy, compras tabla)
completada | credito | parcial | cancelada | pendiente
```

---

## Contratos de Interface

### TraditionalPurchaseUC.execute(cmd: RegisterPurchaseCommand) → PurchaseResult
- `cmd.doc_type == DIRECT` → llama RegistrarCompraUC → afecta inventario/GL/CXP
- `cmd.doc_type == PR` → llama PurchaseRequestUC.crear_pr() → SIN inventario/GL/CXP
- `cmd.doc_type == PO` → llama PurchaseRequestUC.convertir_a_po() → SIN inventario/GL/CXP

### ReceivePOAdapter.register_partial_receipt(po_id, items, usuario, sucursal_id, proveedor_id) → ReceiptResult
- Valida PO en estado receivable
- Llama add_stock() por item
- Llama registrar_lote() si lote presente
- Actualiza PO estado (PARCIAL/RECIBIDA)
- Crea compra via PurchaseService (con GL/CXP)
- Publica RECEPCION_CONFIRMADA
