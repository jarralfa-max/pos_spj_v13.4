# FASE 0 — Auditoría Módulo Compras
> Generada: 2026-05-15 | Repo: pos_spj_v13.4

---

## 1. Mapa de Archivos

| Archivo | Responsabilidad | Estado |
|---------|----------------|--------|
| `modulos/compras_pro.py` | UI principal (3 tabs) | Activo — 3 500+ LOC |
| `modulos/recepcion_qr_widget.py` | UI QR / Recepción (4 tabs + submodo PO en Recepcionar) | Activo — QR NO-TOUCH |
| `modulos/design_tokens.py` | Sistema de colores y tokens | Activo |
| `modulos/spj_styles.py` | Funciones de estilo (apply_spj_buttons, etc.) | Activo |
| `core/services/purchase_service.py` | Servicio principal de registro de compra | Activo — canónico |
| `application/use_cases/registrar_compra_uc.py` | Use case compra tradicional | Activo — canónico |
| `application/purchases/traditional_purchase_uc.py` | Router DIRECT/PR/PO | Activo — Fase 2 |
| `application/purchases/purchase_request_uc.py` | UC de PR (create/approve/reject/convert) | Activo — Fase 3 |
| `application/purchases/purchase_order_uc.py` | UC de PO (create/receive/cancel) | Activo — Fase 4 |
| `application/purchases/receive_po_adapter.py` | Adaptador recepción PO | Activo — Fase 4 |
| `application/purchases/commands.py` | DTOs de comando | Activo |
| `application/purchases/states.py` | Enums PRState, POState, DocumentType | Activo |
| `application/purchases/results.py` | PurchaseResult dataclass | Activo |
| `repositories/purchase_repository.py` | Acceso a datos compras | Activo |
| `core/use_cases/compra.py` | UC legado | **DEPRECATED** (Phase 2, 2026-05-15) |

---

## 2. Ruta Oficial de Compra Tradicional

```
UI (ModuloComprasPro._procesar_compra)
  └─ DIRECT → RegistrarCompraUC.execute(DatosCompraDTO)
                └─ PurchaseService.register_purchase()
                    ├─ PurchaseRepository.create_purchase()       → compras
                    ├─ PurchaseRepository.save_purchase_items()   → detalles_compra
                    ├─ EventBus.publish(PURCHASE_ITEMS_PROCESS)   → PurchaseInventoryHandler
                    │     └─ inventory_service.add_stock()        → kardex + inventario_actual
                    ├─ _crear_lotes_compra()                      → lotes + movimientos_lote
                    ├─ finance_service.crear_cxp() [si deuda]     → accounts_payable
                    ├─ finance_service.registrar_asiento()        → asientos (GL)
                    └─ EventBus.publish(COMPRA_REGISTRADA)        → PurchaseFinanceHandler (async)

  └─ PR → TraditionalPurchaseUC.execute(RegisterPurchaseCommand{doc_type=PR})
            └─ PurchaseRequestUC.crear_pr()
                ├─ INSERT purchase_requests                        [SIN inventario]
                ├─ INSERT purchase_request_items                   [SIN GL]
                └─ audit_write()                                   [SIN CXP]

  └─ PO → TraditionalPurchaseUC.execute(RegisterPurchaseCommand{doc_type=PO})
            └─ PurchaseRequestUC.convertir_a_po()
                ├─ INSERT ordenes_compra                           [SIN inventario]
                ├─ INSERT ordenes_compra_items                     [SIN GL]
                └─ audit_write()                                   [SIN CXP]
```

### Ruta QR (NO-TOUCH):
```
UI (RecepcionQRWidget._procesar_recepcion_en_bd)
  ├─ INSERT recepciones
  ├─ INSERT recepcion_items
  ├─ UPSERT inventario_actual            → stock físico
  ├─ UPDATE productos.existencia
  ├─ INSERT movimientos_inventario       → kardex
  ├─ UPDATE trazabilidad_qr             → estado='recibido'
  └─ UPDATE contenedores_qr             → estado='disponible'
```

### Ruta Recepción PO (Fase 4):
```
UI (RecepcionQRWidget submodo PO → _confirmar_recepcion_po)
  └─ ReceivePOAdapter.register_partial_receipt()
      ├─ inventory_service.add_stock()   → kardex + inventario
      ├─ lote_service.registrar_lote()   → lotes
      ├─ purchase_order_repo.update_item_received()
      ├─ purchase_order_repo.compute_po_completion() → estado PO
      ├─ PurchaseService.register_purchase()         → compras + GL + CXP
      └─ EventBus.publish(RECEPCION_CONFIRMADA)
```

---

## 3. Tablas DB Tocadas por Módulo Compras

| Tabla | Quién escribe | Notas |
|-------|--------------|-------|
| `compras` | PurchaseRepository | Folio único, purchase_order_id (078) |
| `detalles_compra` | PurchaseRepository | Items de compra |
| `purchase_requests` | PurchaseRequestUC | Nueva (076) |
| `purchase_request_items` | PurchaseRequestUC | Nueva (076) |
| `ordenes_compra` | PurchaseOrderUC | Extendida (077) |
| `ordenes_compra_items` | PurchaseOrderUC | Extendida (077) |
| `lotes` | PurchaseService._crear_lotes_compra | Auto-creados |
| `movimientos_lote` | PurchaseService._crear_lotes_compra | Trazabilidad lotes |
| `kardex` | InventoryService (via add_stock) | Movimiento físico |
| `inventario_actual` | RecepcionQRWidget (UPSERT) / InventoryService | Stock real |
| `productos` | RecepcionQRWidget (UPDATE existencia) | Cache de stock |
| `movimientos_inventario` | RecepcionQRWidget | Kardex QR |
| `recepciones` | RecepcionQRWidget | Registro recepción física |
| `recepcion_items` | RecepcionQRWidget | Items recibidos |
| `trazabilidad_qr` | RecepcionQRWidget | Estado contenedor |
| `contenedores_qr` | RecepcionQRWidget | Lifecycle contenedor |
| `accounts_payable` | FinanceService.crear_cxp | CXP si deuda |
| `asientos` | FinanceService.registrar_asiento | GL doble entrada |
| `audit_logs` | AuditService | Trail de auditoría |
| `temp_purchase_drafts` | PurchaseRepository | Borradores por user/sucursal |
| `plantillas_compra` | UI directa | SQL en UI (debt técnica) |

---

## 4. SQL Directo en UI — Deuda Técnica

`compras_pro.py` contiene SQL directo en ~20 ubicaciones:

| Ubicación aprox. | Qué hace | Riesgo |
|-----------------|---------|--------|
| L424-434 | `_HistorialLoader.run()` SELECT historial | Bajo — hilo separado |
| L1281-1282 | Datos proveedor (RFC, dirección, teléfono) | Medio |
| L1412-1413 | COUNT/SUM por sucursal | Bajo — lectura |
| L1486-1487 | Plantillas lista | Bajo — lectura |
| L1511-1512 | Items plantilla | Bajo — lectura |
| L1771-1772 | Sucursales | Bajo — lectura |
| L2428-2429 | Verificación folio duplicado | Medio |
| L2576-2584 | Detección recetas en items | Bajo — lectura |
| L2609-2627 | Componentes de recetas | Bajo — lectura |

**`recepcion_qr_widget.py` contiene SQL crítico:**

| Ubicación aprox. | Qué hace | Riesgo |
|-----------------|---------|--------|
| L777-793 | SELECT PO abiertas (Fase 6) | Bajo — lectura |
| L1647-1659 | INSERT recepciones | **ALTO — mutación** |
| L1668-1673 | INSERT recepcion_items | **ALTO — mutación** |
| L1677-1689 | UPSERT inventario_actual | **ALTO — inventario** |
| L1693-1700 | UPDATE productos.existencia | **ALTO — stock** |
| L1703-1709 | INSERT movimientos_inventario | **ALTO — kardex** |
| L1712-1716 | UPDATE trazabilidad_qr | **ALTO — trazabilidad** |
| L1720-1725 | UPDATE contenedores_qr | MEDIO |

> **QR NO-TOUCH**: Este SQL en recepcion_qr_widget.py es la lógica QR existente. No se toca.

---

## 5. Riesgos de Duplicidad Detectados

### CRÍTICO (resuelto): ProcesarCompraUC duplica GL + CXP
- `core/use_cases/compra.py` llama PurchaseService (que ya hace GL+CXP) Y LUEGO duplica los asientos
- **Resolución**: Marcado DEPRECATED. No llamar. Alias `container.uc_compra` apunta a UC correcto.

### ALTO (mitigado): add_stock doble si handler + fallback
- PurchaseService tiene guardia: si handler registrado → pub event, si no → llamada directa
- **Resolución**: Mutuamente excluyente. Guarda en línea 76 de purchase_service.py.

### MEDIO: recepciones.purchase_order_id faltante
- La tabla `recepciones` no tiene FK a `ordenes_compra`
- Rastreo PO→Recepción solo posible vía `compras.purchase_order_id`
- **Plan**: Migración 079 si hace falta trazabilidad directa PO→recepción

### BAJO: compras.document_type faltante
- No se puede distinguir a nivel DB si una compra vino de PR, PO o DIRECT
- **Plan**: Migración 080 para agregar columna `document_type` con DEFAULT 'DIRECT'

---

## 6. Eventos de Dominio

| Evento | Tipo | Quién publica | Quién consume |
|--------|------|--------------|--------------|
| `PURCHASE_ITEMS_PROCESS` | Sync | PurchaseService | PurchaseInventoryHandler → add_stock |
| `COMPRA_REGISTRADA` / `PURCHASE_CREATED` | Async | PurchaseService | PurchaseFinanceHandler → GL + CXP |
| `RECEPCION_CONFIRMADA` | Async | ReceivePOAdapter | (custom) |

**Handlers legacy removidos** (2026-05-08): `_compra_stock`, `_compra_egreso` — prevenían doble posting.

---

## 7. Sistema de Temas

- Sin clase `ThemeManager` dedicada
- Funciones en `modulos/spj_styles.py`: `apply_spj_buttons()`, `apply_global_theme()`, `apply_theme_dialogs()`
- Tokens: `modulos/design_tokens.py` → `Colors.*` (30+ atributos)
- Política: usar `Colors.*` en todo código nuevo, nunca hex literales sueltos

---

## 8. Estado de Fases Implementadas

| Fase | Descripción | Estado |
|------|-------------|--------|
| Fase 2 | Unificación ruta oficial UC | ✅ TraditionalPurchaseUC canónico |
| Fase 3 | Modelo documental PR | ✅ PurchaseRequestUC + tabla purchase_requests |
| Fase 4 | Modelo documental PO + ReceivePOAdapter | ✅ PurchaseOrderUC + receive_po_adapter |
| Fase 5 | UI selector doc_type (DIRECT/PR/PO) | ✅ _build_doctype_toolbar en compras_pro.py |
| Fase 6 | UI recepción PO en QR widget | ✅ submodo `_build_po_reception_panel` en `📦 3. Recepcionar` |
| Fase 7 | Historial con timeline + filtro tipo_doc | ✅ _refresh_hist_timeline, 9 cols, badges |
| Fase 8 | Recepción con QR apta para PO | ✅ selector de origen interno QR/PO/Transferencia |
| Fase 9 | Historial documental | ✅ timeline PR/PO/recepción + filtros + CSV desde cache |
| Fase 10 | Pruebas, limpieza y documentación final | ✅ suite purchases + dead code cleanup + docs finales |
