# AUDITORÍA MÓDULO COMPRAS — pos_spj v13.4
> Generado: 2026-05-15 | Fase 0 — Pre-refactor

---

## 1. MAPA DE ARCHIVOS INVOLUCRADOS

### Capa UI (Presentación)
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `modulos/compras_pro.py` | 3 374 | Widget principal — ComprasWidget |
| `modulos/planeacion_compras.py` | 318 | Dashboard de planificación ML |

**Problemas detectados en compras_pro.py:**
- SQL embebido en al menos 5 métodos del widget
- Lógica de cálculo de IVA (16 %) hardcodeada en UI
- Lógica de recetas disparada desde UI directamente
- Lógica de costo/varianza (>20 %) dentro del widget
- Borrador en JSON plano (`~/.spj_compra_borrador.json`) + tabla DB (coexistencia)

### Capa Repositorio
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `repositories/purchase_repository.py` | 295 | CRUD compras + detalles + borradores |

### Capa Servicio
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `core/services/purchase_service.py` | 335 | Orquestador — registro compra |
| `core/services/inventory_service.py` | 206 | add_stock |
| `core/services/lote_service.py` | 180 | Lotes FIFO |
| `core/services/enterprise/finance_service.py` | 1 920 | GL + CxP |
| `core/services/compras_inventariables_engine.py` | 115 | Activos fijos |
| `core/services/recipe_engine.py` | — | Explosión de recetas |

### Capa Use Case
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `application/use_cases/registrar_compra_uc.py` | 217 | UC de alto nivel (Clean Arch) |
| `core/use_cases/compra.py` | 236 | UC de bajo nivel + GL directo |

> ⚠️ **DUPLICIDAD DETECTADA:** Existen DOS use cases para la misma operación.
> `RegistrarCompraUC` y `ProcesarCompraUC` comparten responsabilidades superpuestas.
> La UI usa `purchase_service` directamente (no pasa por ningún UC).

### Capa Dominio
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `domain/entities/purchase.py` | 41 | Entities PurchaseItem + Purchase |

### Capa Eventos
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `core/events/event_bus.py` | 12 392 | Bus principal |
| `core/events/domain_events.py` | 60 | Aliases de eventos |
| `core/events/handlers/purchase_handler.py` | 108 | Handlers inventario + finanzas |
| `core/events/wiring.py` | — | Suscripción de handlers |

### Capa QR / Trazabilidad
| Archivo | Líneas | Rol |
|---------|--------|-----|
| `services/qr_service.py` | 188 | Generación y escaneo QR |

### Tablas de base de datos
| Tabla | Propósito |
|-------|-----------|
| `compras` | Cabecera de compra |
| `detalles_compra` | Partidas de compra |
| `temp_purchase_drafts` | Borradores DB |
| `lotes` | Control de lotes |
| `movimientos_lote` | FIFO de lotes |
| `trazabilidad_qr` | Contenedores QR |
| `movimientos_trazabilidad` | Historia QR |
| `plantillas_compra` | Plantillas de compra |
| `compras_inventariables` | Activos fijos |

---

## 2. RUTA ACTUAL DE COMPRA TRADICIONAL

```
ComprasWidget._procesar_compra()
    └─► PurchaseService.register_purchase()
            ├─► purchase_repo.create_purchase()        → INSERT compras
            ├─► purchase_repo.save_purchase_items()    → INSERT detalles_compra
            ├─► EventBus.publish(PURCHASE_ITEMS_PROCESS)
            │       └─► PurchaseInventoryHandler       → inventory_service.add_stock()
            └─► EventBus.publish_async(PURCHASE_CREATED)
                    └─► PurchaseFinanceHandler          → finance_service.registrar_asiento()
```

**Afectación de inventario:**
- Se ejecuta **dentro del SAVEPOINT** via `PURCHASE_ITEMS_PROCESS` (prioridad 100)
- `inventory_service.add_stock()` actualiza `stock` / `kardex`

**Afectación de finanzas:**
- Asiento `1201/2101` (Mercancías IN / CxP) — siempre
- Asiento `2101/1101` (CxP / Efectivo) — solo si CONTADO y monto_pagado > 0
- CxP creado si deuda > 0 (vía `finance_service.crear_cxp()`)

**Afectación de lotes:**
- `ProcesarCompraUC` NO crea lotes directamente
- Los lotes se crean si la UI llama `lote_service.registrar_lote()` (flujo QR)
- En compra tradicional: lotes opcionales (`detalles_compra.lote` TEXT)

---

## 3. RUTA ACTUAL DE FLUJO QR

```
ComprasWidget (Tab QR)
    ├─► qr_service.qr_contenedor_proveedor()  → genera QR → trazabilidad_qr
    └─► qr_service.escanear_recepcion()       → marca recibido → inventario si peso_kg
```

**El flujo QR es INDEPENDIENTE del flujo Compra Tradicional.**
No comparten SAVEPOINT ni handlers de inventario.

---

## 4. AFECTACIONES POR OPERACIÓN

| Operación | Inventario | CxP/Finanzas | Lotes | Eventos | Auditoría |
|-----------|-----------|-------------|-------|---------|-----------|
| Compra Tradicional | ✅ (PURCHASE_ITEMS_PROCESS) | ✅ (PURCHASE_CREATED) | Opcional | 2 eventos | ✅ |
| Recepción QR | ✅ (qr_service) | ❌ | ✅ (lote_service) | RECEPCION_CONFIRMADA | Parcial |
| PR (nuevo) | ❌ DEBE SER | ❌ DEBE SER | ❌ | PR_CREADA (nuevo) | ✅ |
| PO (nuevo) | ❌ DEBE SER | ❌ DEBE SER | ❌ | PO_CREADA (nuevo) | ✅ |

---

## 5. DUPLICIDADES DETECTADAS

### 5.1 Dos Use Cases para la misma operación
- `RegistrarCompraUC` (application/use_cases/) — Clean Arch, llama PurchaseService
- `ProcesarCompraUC` (core/use_cases/) — Legacy, llama PurchaseService + GL directo

**Riesgo:** La UI actual NO usa ninguno de los dos UC; llama `PurchaseService` directamente.
**Decisión (Fase 2):** Unificar. Ruta oficial: `RegistrarCompraUC` como punto de entrada.

### 5.2 Doble borrador
- `~/.spj_compra_borrador.json` (archivo plano)
- `temp_purchase_drafts` (tabla DB)
Ambos coexisten. La migración 073 agregó la tabla pero la UI sigue usando JSON.

### 5.3 GL duplicado potencial
Si la UI llama `ProcesarCompraUC` Y `PurchaseService` publica `PURCHASE_CREATED`,
se ejecutarían dos asientos GL. La UI DEBE usar un solo punto de entrada.

---

## 6. PERMISOS ACTUALES

| Rol | procesar | cancelar | reabrir | editar | exportar | borrador | historial |
|-----|---------|---------|--------|-------|---------|---------|---------|
| ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GERENTE | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SUPERVISOR | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| COMPRAS | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| ALMACEN | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| CAJERO | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

> Los nuevos permisos `aprobar_pr` y `generar_po` deberán agregarse en Fase 2.

---

## 7. SCHEMA MIGRATIONS RELEVANTES

| Migración | Descripción |
|-----------|-------------|
| 071 | Agrega condicion_pago, plazo_dias, moneda a compras |
| 072 | CHECK constraint en condicion_pago |
| 073 | Tabla temp_purchase_drafts |
| 074 | Campo archivo_adjunto en compras |
| 075 | Plantillas de compra |

> Las migraciones para PR/PO (nuevas tablas) se planifican en Fase 3.

---

## 8. TESTS EXISTENTES

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_purchase_repository.py` | ~15 | create, save_items, get_by_folio, draft CRUD |
| `test_uc_compra.py` | ~12 | ProcesarCompraUC — GL, CxP, eventos |
| `test_flujo_completo.py` | E2E | Flujo completo de venta/compra |
| `test_inventory.py` | ~20 | add_stock, kardex |

> Faltan tests de caracterización para:
> - Comportamiento actual sin mocks (integration)
> - Efectos en finanzas con datos reales
> - No-regresión QR
> - Contrato PR/PO (pre-implementación)
