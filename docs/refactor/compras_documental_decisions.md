# DECISIONES DOCUMENTALES — COMPRAS ERP
> pos_spj v13.4 | 2026-05-15

---

## Contexto

El módulo de compras actual soporta únicamente compra directa (un solo paso).
El objetivo es evolucionar hacia un flujo documental ERP sin romper la operación actual.

---

## Decisión 1: Flujo documental completo en Compra Tradicional

**Decisión:** PR → APROBACIÓN → PO → RECEPCIÓN → INVENTARIO → CXP

**Justificación:**
- Alinea con estándares ERP (SAP S/4HANA, Odoo, NetSuite)
- Permite control de presupuesto antes de comprometer compra
- Permite recepción parcial trazada contra PO
- Mantiene compatibilidad con compra directa existente (bypass opcional)

**Implementación:**
- Nuevas tablas: `purchase_requests` (PR) y `purchase_orders` (PO)
- La tabla `compras` existente sigue siendo el registro de recepción/compra real
- Una PO puede generar una o varias recepciones (parciales)
- Una recepción puede estar asociada a una PO o ser compra directa (PO=NULL)

---

## Decisión 2: Compra directa preservada

**Decisión:** El flujo actual de compra directa (sin PR/PO) se CONSERVA.

**Justificación:**
- Operaciones urgentes que no requieren aprobación
- Compatibilidad con workflow actual de almacén
- Sin interrupción operativa durante transición

**Implementación:**
- Botón "Procesar compra directa" disponible según permisos
- Solo para roles ADMIN/GERENTE/SUPERVISOR
- La compra directa crea `compras` sin `purchase_order_id`

---

## Decisión 3: Una sola ruta de afectación de inventario

**Decisión:** El inventario SE AFECTA ÚNICAMENTE en la recepción física.
Ni PR ni PO tocan inventario.

**Justificación:**
- Evita doble inventario (PR reserva ≠ stock real)
- Consistencia con estándar ERP
- Un solo punto de control (PurchaseInventoryHandler)

**Contrato:**
- `purchase_requests` → estado en DB, sin efectos en inventario
- `purchase_orders` → estado en DB, sin efectos en inventario
- `compras` (recepción) → dispara `PURCHASE_ITEMS_PROCESS` → `add_stock()`

---

## Decisión 4: Una sola ruta de afectación financiera

**Decisión:** CxP y asientos GL SE GENERAN en la recepción/compra, no en PO.

**Justificación:**
- Una PO es una promesa de compra, no una deuda contable
- El pasivo (CxP) surge al recibir la mercancía
- Consistencia con principios contables (devengado)

**Contrato:**
- PR → sin asiento
- PO → sin asiento (puede tener presupuesto comprometido como nota, no asiento)
- Recepción → asiento `1201/2101` + CxP si aplica

---

## Decisión 5: Ruta UC oficial — RegistrarCompraUC

**Decisión:** La ruta oficial es `application/use_cases/registrar_compra_uc.py`.

**Justificación:**
- Es la implementación más alineada con Clean Architecture
- `ProcesarCompraUC` en `core/use_cases/compra.py` queda como wrapper deprecated
- Evita duplicación de asientos GL (el GL se maneja via EventBus, no directamente)

**Plan de unificación (Fase 2):**
1. La UI llama `RegistrarCompraUC.execute()`
2. `ProcesarCompraUC` se convierte en thin wrapper (deprecation notice)
3. El GL posting via `PurchaseFinanceHandler` es el único punto
4. Se elimina el GL directo en `ProcesarCompraUC`

---

## Decisión 6: Nuevas tablas en migraciones incrementales

**Decisión:** PR y PO se implementan en migraciones nuevas (> 075).

**Numeración tentativa:**
- `076_purchase_requests.py` — tabla PR + estados
- `077_purchase_orders.py` — tabla PO + referencia a PR
- `078_compras_po_link.py` — campo `purchase_order_id` en `compras` (nullable)

**Regla:** Toda nueva tabla usa `CREATE TABLE IF NOT EXISTS`.
**Regla:** Todo nuevo campo usa `ADD COLUMN IF NOT EXISTS` (sin romper schema actual).

---

## Decisión 7: Estados documentales

### PR (Purchase Request)
```
BORRADOR           → editable, no enviado
PENDIENTE_APROBACION → enviado, esperando aprobador
APROBADA           → aprobada, lista para generar PO
RECHAZADA          → rechazada con motivo
CONVERTIDA_A_PO    → PO generada desde esta PR
CANCELADA          → cancelada por usuario
```

### PO (Purchase Order)
```
ABIERTA            → PO generada, sin recepción
PARCIAL            → recepción parcial registrada
RECIBIDA           → recepción completa
CERRADA            → cerrada administrativamente
CANCELADA          → cancelada
```

---

## Decisión 8: Permisos nuevos

| Permiso | Descripción | Roles mínimos |
|---------|-------------|---------------|
| `crear_pr` | Crear Purchase Request | COMPRAS, ALMACEN, SUPERVISOR, ADMIN |
| `aprobar_pr` | Aprobar/rechazar PR | GERENTE, ADMIN |
| `generar_po` | Convertir PR aprobada en PO | SUPERVISOR, GERENTE, ADMIN |
| `enviar_a_recepcion` | Enviar PO a recepción | COMPRAS, SUPERVISOR, GERENTE, ADMIN |

Los permisos existentes (`procesar`, `cancelar`, etc.) se mantienen sin cambio.

---

## Decisión 9: Integración QR-PO

**Decisión:** La recepción QR puede recibir PO mediante adaptador mínimo.

**Contrato del adaptador:**
```python
# application/purchases/receive_po_adapter.py
class ReceivePOAdapter:
    def get_po_lines(self, po_id: int) -> list[dict]
    def register_partial_receipt(self, po_id: int, received_items: list[dict]) -> dict
    def get_po_status(self, po_id: int) -> str
```

El adaptador NO reimplementa inventario, lotes ni QR.
Solo lee PO y actualiza su estado llamando servicios existentes.

---

## Riesgos identificados y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| Doble inventario (PR/PO tocando stock) | Alta sin control | Crítico | Tests de contrato pre-implementación |
| Doble asiento GL (2 UCs activos) | Media | Alto | Unificar UC en Fase 2 antes de cualquier UI |
| Doble CxP | Media | Alto | Garantizar un solo punto de `crear_cxp()` |
| Doble QR (nuevo motor) | Baja si se respeta política | Crítico | Política QR No-Touch |
| Dark/Light roto | Media | Medio | Usar solo ThemeManager tokens |
| Schema break en compras legacy | Baja | Alto | Campos nuevos nullable, sin romper ALTER |
| Borrador JSON vs DB inconsistente | Baja | Bajo | Unificar a DB en Fase 5 |
