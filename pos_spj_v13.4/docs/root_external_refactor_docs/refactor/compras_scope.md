# ALCANCE REFACTORIZACIÓN COMPRAS — pos_spj v13.4
> Versión: 1.0 | Fecha: 2026-05-15

---

## ✅ QUÉ SE MODIFICA (lógica funcional)

### Tab 1 — Compra Tradicional
- Flujo documental: BORRADOR → PR → APROBACIÓN → PO → RECEPCIÓN → INVENTARIO → CXP
- Estados de PR: BORRADOR, PENDIENTE_APROBACION, APROBADA, RECHAZADA, CONVERTIDA_A_PO, CANCELADA
- Estados de PO: ABIERTA, PARCIAL, RECIBIDA, CERRADA, CANCELADA
- Layout de 3 columnas (lista documental | captura | partidas/totales)
- Botón dinámico según estado del documento
- Unificación de ruta UC (eliminar duplicidad RegistrarCompraUC vs ProcesarCompraUC)

---

## 🟡 QUÉ SE ADAPTA (mínimo necesario)

### Tab 2 — Recepción QR
- Agregar selector/entrada para recibir desde PO
- Visualización de PO asociada al contenedor
- Comparación esperado vs recibido contra líneas de PO
- Estado de recepción parcial/completa por PO
- Adaptador mínimo: `application/purchases/receive_po_adapter.py`
  - Lee PO y expone líneas esperadas
  - Llama servicios existentes de recepción/inventario/kardex/lotes
  - Actualiza estado de PO
  - NO duplica lógica QR ni movimientos

---

## 🎨 QUÉ SE MEJORA SOLO EN UI/UX (sin tocar lógica)

### Tab 2 — Flujo QR / Recepción QR
- Reorganización visual acorde a referencia entregada
- Soporte dark/light via ThemeManager existente
- Eliminación de colores hex hardcodeados si los hubiera
- Ordenamiento visual de etapas: Identificar → Asignar → Recibir

### Tab 3 — Histórico
- Filtros mejorados (fecha, estado, proveedor, sucursal)
- Badges de estado estandarizados
- Timeline documental (si servicios existentes lo permiten)
- Exportación (si ya existe)

---

## ❌ QUÉ NO SE TOCA

| Componente | Razón |
|-----------|-------|
| Motor QR (`qr_service.py`) | Core de trazabilidad — no se reescribe |
| Lógica de contenedores | Intacta |
| Reglas de asignación QR | Intactas |
| Lógica de recepción física actual | Reutilizada, no duplicada |
| `inventory_service.add_stock()` | Punto único de afectación de inventario |
| `lote_service.registrar_lote()` | Punto único de creación de lotes |
| `finance_service.registrar_asiento()` | Punto único de GL |
| `finance_service.crear_cxp()` | Punto único de CxP |
| `EventBus` handlers de compra | No se crean handlers duplicados |
| Transferencias existentes | No se duplican |
| Schema `compras` / `detalles_compra` | Reutilizados |
| Permisos actuales (roles) | Extendidos, no reemplazados |
| Auditoría existente | Extendida, no reemplazada |

---

## 📐 REGLAS DE DISEÑO

### Lo que PR debe hacer
- Crear documento PR (tabla `purchase_requests` — nueva)
- No afectar inventario
- No generar CxP
- No generar asiento GL
- Publicar evento `PR_CREADA` (nuevo)

### Lo que PO debe hacer
- Crear documento PO referenciando PR (tabla `purchase_orders` — nueva)
- Comprometer la compra documentalmente
- No afectar inventario
- No generar movimiento físico
- Publicar evento `PO_CREADA` (nuevo)
- Quedar disponible para la pestaña de recepción

### Lo que Recepción debe hacer
- Afectar inventario (vía `inventory_service.add_stock()` existente)
- Crear lotes si aplica (vía `lote_service.registrar_lote()` existente)
- Actualizar estado de PO (PARCIAL / RECIBIDA)
- Generar CxP si corresponde (vía `finance_service.crear_cxp()` existente)
- Publicar `RECEPCION_CONFIRMADA` existente
- Puede iniciar desde: contenedor QR existente | PO enviada desde Compra Tradicional

---

## 🗺️ RUTAS OFICIALES (objetivo)

```
Compra Tradicional PR/PO:
UI → RegistrarCompraUC (ruta oficial) → PurchaseService → repositorios/servicios

QR (sin cambio):
UI QR → qr_service → inventory/lotes existentes

Recepción PO (adaptador):
UI Recepción → receive_po_adapter → lógica recepción/inventario existente
```

---

## 📋 FASES Y ENTREGABLES

| Fase | Entregable | Estado |
|------|-----------|--------|
| 0 | Auditoría + Documentación | ✅ Esta entrega |
| 1 | Tests de caracterización | ✅ Esta entrega |
| 2 | Unificar UC Compra Tradicional | ⏳ |
| 3 | Modelo documental PR/PO | ⏳ |
| 4 | Adaptador Recepción PO | ⏳ |
| 5 | UI Compra Tradicional (3 cols) | ⏳ |
| 6 | UI QR/Recepción mejorada | ⏳ |
| 7 | UI Histórico mejorado | ⏳ |
