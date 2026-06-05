# VENTAS — Auditoría de Refactor (FASE 0)

Fecha: 2026-05-27  
Alcance auditado:
- `pos_spj_v13.4/modulos/ventas.py`
- `pos_spj_v13.4/core/use_cases/venta.py`
- `pos_spj_v13.4/core/services/sales_service.py`
- `pos_spj_v13.4/core/services/sales_reversal_service.py`
- `pos_spj_v13.4/core/events/domain_events.py`
- `pos_spj_v13.4/core/events/event_bus.py`
- referencias de eventos/handlers en `core/events/wiring.py` y flujos relacionados detectados por búsqueda.

> **Importante (FASE 0):** este documento solo mapea riesgos y propone migración incremental. No se cambió lógica de negocio.

---

## 1) Métodos en `modulos/ventas.py` con SQL directo

### Lectura (SELECT)
- `actualizar_completer_model` (consulta clientes para autocompletado).
- `_cargar_categorias` (consulta categorías desde `productos`).
- `cargar_productos_interactivos` (consulta catálogo/productos y stock mostrado).
- `_cargar_hardware_config` (consulta configuración de hardware/ticket).
- `_log_scan` (consulta `trazabilidad_qr`).
- `_reimprimir_ultima_venta` (consulta `ventas` y `detalles_venta`).
- `_guardar_pdf_auditoria_ultima_venta` (consulta `ventas`).
- `_buscar` (consulta `ventas` y detalle para soporte de cancelación).
- `_cfg` (consulta configuraciones de ticket).

### Escritura (INSERT/UPDATE/COMMIT)
- `guardar_nuevo_cliente`:
  - `INSERT INTO clientes`
  - `INSERT OR IGNORE INTO tarjetas_fidelidad`
  - `commit()` directo desde UI
- `_cancelar` mantiene explícitamente una protección para **no** hacer `UPDATE` directo de estado (correcto como guardrail), pero evidencia que antes existía esa ruta.

**Riesgo:** Alto. Mezcla UI + persistencia con commits directos en pantalla de ventas.
**Prioridad:** P0–P1.

---

## 2) Métodos que modifican estado de dominio desde UI (`modulos/ventas.py`)

### Carrito
- `agregar_al_carrito`, `eliminar_producto_carrito`, `cancelar_venta`, `_quitar_descuento_item`, `_quitar_descuento_por_uid`, `_descuento_rapido`, `_descuento_custom`, `actualizar_tabla_compras`.

### Cliente/Fidelidad
- `seleccionar_cliente`, `limpiar_cliente`, `guardar_nuevo_cliente`.
- En flujo de cobro hay actualización visual de puntos y consultas de saldo post-venta.

### Pagos/Descuentos
- `cobrar_venta` (orquesta diálogo, arma payload, rutas alternas UC/servicio legacy).
- `_descuento_rapido`, `_descuento_custom`.

### Tickets
- `_imprimir_ticket_consolidado`, `_imprimir_ticket_hardware`, `generar_ticket`, `guardar_ticket_pdf`, `generar_html_ticket`, `_reimprimir_ultima_venta`, `_guardar_pdf_auditoria_ultima_venta`.

### Reservas
- `suspender_venta` (reserva stock y publica eventos de reserva).
- `reanudar_venta`.
- `cancelar_venta` (libera reserva activa y publica eventos).

### Inventario
- Verificación de stock previa al agregado de carrito y uso de `stock_reservas` en suspensión/confirmación/cancelación.

**Riesgo:** Alto por cohesión baja y reglas de negocio distribuidas.
**Prioridad:** P0.

---

## 3) Métodos que llaman directamente a `SalesService`

En `modulos/ventas.py`:
- `cobrar_venta`:
  - Ruta preferida: `ProcesarVentaUC.ejecutar(...)`.
  - Fallback legacy: `self.container.sales_service.execute_sale(...)`.

En `core/use_cases/venta.py`:
- `ProcesarVentaUC.ejecutar` invoca `self._sales.execute_sale(...)` como backend transaccional.

**Riesgo:** Medio-Alto por doble ruta efectiva (UC vs fallback directo).
**Prioridad:** P0.

---

## 4) Métodos que **deberían** llamar canónicamente a `ProcesarVentaUC`

- `modulos/ventas.py::cobrar_venta` (ya lo intenta, pero mantiene bypass).
- Cualquier adapter externo que hoy llame `SalesService.execute_sale` directamente (WhatsApp/delivery/webhook) debe converger a UC + adapters de compatibilidad.

**Gap actual:** existe fallback directo a `sales_service.execute_sale` en UI.

---

## 5) Métodos que mezclan UI + lógica de negocio

Críticos en `modulos/ventas.py`:
- `cobrar_venta` (armado de payload, selección de ruta, reglas de crédito/pago/puntos, impresión, reservas, publicación de eventos).
- `actualizar_totales` (cálculo subtotal/descuento/total/puntos en UI).
- `agregar_al_carrito` (stock + pricing por ítem + UID + reglas de agregado).
- `guardar_nuevo_cliente` (persistencia transaccional desde UI).
- `suspender_venta` / `reanudar_venta` / `cancelar_venta` (reglas de reserva + eventos).
- bloque de ticketing (`generar_html_ticket`, impresión, PDF) con consulta de configuración.

**Riesgo:** Alto.
**Prioridad:** P0–P1.

---

## 6) Duplicados detectados (fuentes múltiples de verdad)

### Cálculo de total / descuentos
- UI (`ventas.py`) calcula totales y descuentos para display y payload.
- UC (`ProcesarVentaUC`) recalcula subtotal/total.
- `SalesService` vuelve a normalizar/calcular internamente.

### Cálculo de cambio / pago
- UI/diálogo de pago calcula y valida preview.
- `SalesService.execute_sale` valida pago final.

### Puntos fidelidad
- UI calcula/preview de puntos y actualiza labels.
- `SalesService` aplica canje y/o acredita según flujo.
- documentación/comentarios indican handlers post-venta potencialmente acreditan también.

### Validación de stock
- UI valida antes de agregar/cobrar.
- UC valida pre-chequeo.
- `SalesService` valida en la transacción de venta.

### Validación de crédito
- UI prepara datos de crédito.
- `SalesService` valida y registra condiciones financieras.

### Generación de ticket
- `SalesService.execute_sale` retorna ticket.
- UC regenera ticket si falta.
- UI vuelve a construir/imprimir/guardar ticket.

**Riesgo:** Alto por divergencia e inconsistencias.
**Prioridad:** P0.

---

## 7) Eventos publicados por ventas (mapa actual)

### Desde `SalesService` / flujo transaccional
- `SALE_ITEMS_PROCESS` (evento transaccional estricto, dentro de savepoint/tx).
- `VENTA_COMPLETADA`/aliases `SALE_COMPLETED` (post-commit/downstream).

### Desde UI (`modulos/ventas.py`) en reservas/suspensión
- `VENTA_SUSPENDIDA`
- `STOCK_RESERVADO`
- `VENTA_CONFIRMADA_RESERVA`
- `STOCK_DESCONTADO_RESERVA`
- `VENTA_SUSPENDIDA_CANCELADA`
- `STOCK_RESERVA_LIBERADA`

### Desde reversas (`sales_reversal_service.py`)
- `VENTA_CANCELADA`
- (y equivalentes de refund/credit note según `_fire_event` por operación)

### Catálogo y alias (`domain_events.py` + `event_bus.py`)
- coexistencia de nombres legacy ES, aliases EN y eventos lowercase modernos (`loyalty_points_*`, etc.).

**Riesgo:** Medio-Alto (semánticas solapadas y ambigüedad tx vs post-commit).
**Prioridad:** P1.

---

## 8) Handlers que escuchan eventos de venta (resumen)

Se detecta en wiring/event system:
- handlers financieros/caja/tesorería atados a `VENTA_COMPLETADA`.
- handlers potenciales de fidelidad post-venta.
- handlers de inventario/proceso de ítems sobre `SALE_ITEMS_PROCESS` (strict).

**Riesgo clave:** posible doble efecto si una misma responsabilidad vive en `SalesService` y en handler post-evento.
**Prioridad:** P0–P1.

---

## 9) Tablas escritas durante una venta (consolidado de rutas detectadas)

### Núcleo venta
- `ventas`
- `detalles_venta`
- `payments`

### Inventario / reservas
- `inventory_movements` (vía handlers/engine)
- tablas de reservas (vía servicio de reservas de stock)

### Caja/finanzas
- `movimientos_caja`
- posibles rutas: `financial_documents`, `accounts_receivable`/`cuentas_por_cobrar`, `journal_entries`, `treasury_*` (según handler/servicio conectado)

### Fidelidad
- `clientes` (puntos)
- `historico_puntos`

### Sincronización/auxiliares
- tablas de sync/outbox según integración activa.

**Riesgo:** Alto por multiplicidad de writers.
**Prioridad:** P0.

---

## 10) Tablas escritas durante cancelación/devolución (`sales_reversal_service.py`)

- `ventas` (estado)
- `sale_refunds`
- `credit_notes`
- `movimientos_caja`
- `inventory_movements` (vía `InventoryEngine`)
- `clientes` (reversión de puntos)
- `historico_puntos`

**Riesgo:** Alto. `SalesReversalService` toca inventario + caja + fidelidad de forma directa; requiere políticas/servicios canónicos para evitar duplicidad.
**Prioridad:** P0.

---

## Matriz de riesgo y prioridad

| Hallazgo | Riesgo | Impacto | Prioridad |
|---|---:|---:|---:|
| SQL y commit directo en UI ventas | Alto | Alto | P0 |
| Doble ruta de cobro (UC + SalesService directo) | Alto | Alto | P0 |
| Duplicidad de cálculo total/pago/stock/puntos | Alto | Alto | P0 |
| Doble acreditación/canje de fidelidad potencial | Alto | Alto | P0 |
| Ambigüedad de eventos (legacy/alias/lowercase) | Medio-Alto | Alto | P1 |
| Escrituras financieras paralelas CxC | Alto | Alto | P0 |
| Reversas con responsabilidades cruzadas | Alto | Alto | P0 |

---

## Propuesta de migración incremental (sin ruptura)

1. **Canonizar entrada:** forzar `ProcesarVentaUC` como puerta de entrada y dejar adapter legacy explícito temporal.
2. **Separar lectura UI:** extraer query services de productos/clientes y reemplazar SELECT de `ventas.py` por llamadas a servicio.
3. **Centralizar cálculos:** `CartCalculator` + `PaymentPolicy` + DTOs canónicos.
4. **Unificar fidelidad:** una sola política (preview, redeem, earn, reverse) con `operation_id`.
5. **Endurecer `SalesService.execute_sale`:** orquestador legible + límites tx/post-commit claros.
6. **Catalogar eventos:** canonical names, aliases, strictness, idempotencia, payload.
7. **Unificar CxC:** un solo writer para venta crédito (handler financiero canónico).
8. **Reversas compensatorias idempotentes:** delegación por dominio (inventario/finanzas/fidelidad).
9. **Limpieza progresiva de UI:** extraer dialogs/controllers/widgets manteniendo adapters.

---

## Checklist por fase (ejecutable)

### Fase 0 (esta entrega)
- [x] Auditoría automática de SQL en `ventas.py`.
- [x] Mapeo de duplicidades de reglas y rutas de venta.
- [x] Mapeo de eventos y riesgos.
- [x] Documento de auditoría en `docs/refactor/`.

### Fase 1 (siguiente)
- [ ] Consolidar/extender DTOs canónicos en `core/use_cases/venta.py` o `core/use_cases/sales/`.
- [ ] Agregar normalización de métodos de pago y `operation_id` opcional.
- [ ] Pruebas unitarias de DTO/normalización (sin tocar flujo de cobro todavía).
- [ ] Mantener compatibilidad de imports actuales.

### Fase 2+
- [ ] Forzar POS UI → `ProcesarVentaUC`.
- [ ] Remover bypass directo a `SalesService` (con adapter temporal controlado).
- [ ] Continuar según plan maestro por fases 3–12.

---

## Plan exacto de commits propuesto para Fase 1

1. **`feat(sales-dto): consolidar contratos canónicos de venta`**
   - Añadir/expandir DTOs: `ItemCarrito`, `DatosPago`, `ResultadoVenta`, `ClienteVentaDTO`, `PaymentBreakdown`, `LoyaltyRedemptionRequest`, `LoyaltyRedemptionPreview`, `SaleContext`.
   - Normalizadores no disruptivos (método de pago, montos, `operation_id`).
   - Mantener backward compatibility (aliases/campos opcionales).

2. **`test(sales-dto): cubrir construcción y normalización de DTOs`**
   - Tests de efectivo/tarjeta/transferencia/crédito/mixto/MercadoPago.
   - Tests de puntos, descuentos, `cliente_id` opcional, `sucursal_id`, `usuario`, `notas`, `operation_id`.

3. **`docs(refactor): registrar decisiones de DTOs y compatibilidad legacy`**
   - Actualizar `docs/refactor/VENTAS_REFACTOR_AUDIT.md` con estado “Fase 1 completada”.
   - Notas de compatibilidad y adapters.



---

## Re-ejecución controlada (solicitada) — 2026-05-27


### Alcance de esta entrega
- Se **re-ejecutó FASE 0 únicamente** (auditoría + plan).
- **Sin cambios de lógica** en `modulos/ventas.py`, `core/use_cases/venta.py`, `core/services/sales_service.py`, `core/services/sales_reversal_service.py`.

### Validación rápida de hallazgos clave (confirmados)
1. `modulos/ventas.py` mantiene mezcla UI + reglas + consultas DB (catálogo/clientes/tickets/reservas).
2. Persisten rutas múltiples de verdad: UI, UC y `SalesService` (con legado/fallbacks en ecosistema).
3. Fidelidad sigue siendo área de alto riesgo por coexistencia servicio+eventos+UI preview.
4. CxC/finanzas siguen con riesgo de paralelismo entre tablas (`cuentas_por_cobrar`, `accounts_receivable`, `financial_documents`).
5. Catálogo de eventos sigue híbrido (ES/EN/lowercase) y requiere normalización progresiva sin ruptura.

### Plan exacto de commits para Fase 1 (propuesto)
1. `feat(sales-dto): consolidar contratos canónicos de venta`
   - Extender DTOs en `core/use_cases/venta.py` sin romper imports.
   - Incluir `operation_id`, pago mixto, Mercado Pago, descuentos línea/global.
2. `test(sales-dto): cubrir construcción/normalización de DTOs`
   - Tests unitarios para métodos de pago, descuentos, puntos y campos opcionales.
3. `docs(refactor): actualizar estado fase 1 y compatibilidad legacy`
   - Registrar decisiones, adapters y riesgos remanentes.

### Criterio de parada
- Esta entrega **se detiene en FASE 0** por solicitud explícita.
