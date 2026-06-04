# Auditoría Fase 0 — Flujo de ventas v13.4 (sin cambios de lógica)

Fecha: 2026-05-26
Alcance: mapeo de rutas de venta, fidelidad, canje, eventos, inventario, finanzas, CxC, MercadoPago y tests débiles.

## 1) Ruta actual detectada (estado real)

### Ruta A (preferida en UI):
`modulos/ventas.py::finalizar_venta()` → `core/use_cases/venta.py::ProcesarVentaUC.ejecutar()` → `core/services/sales_service.py::SalesService.execute_sale()` → `repositories/sales_repository.py::SalesRepository.create_sale()` → `SALE_ITEMS_PROCESS(strict=True)` → handlers de inventario/finanzas → `RELEASE SAVEPOINT` → `VENTA_COMPLETADA`.

### Ruta B (fallback UI):
`modulos/ventas.py::finalizar_venta()` llama directamente `SalesService.execute_sale()` cuando no hay UC.

### Ruta C (legacy peligrosa):
`repositories/ventas.py::VentaRepository.create_sale()` sigue pudiendo ejecutar inventario/caja/efectos propios si alguien la invoca.

## 2) Hallazgos por tema

### 2.1 Fidelidad (acumulación)
- `ProcesarVentaUC.ejecutar()` aún llama `self._loyalty.process_loyalty_for_sale(...)` (post-venta).
- `SalesService.execute_sale()` aún puede llamar `self.loyalty_service.process_loyalty_for_sale(...)` fuera de la transacción.
- `core/events/wiring.py` también acredita fidelidad en handler `VENTA_COMPLETADA` (`_loyalty_venta`).

**Riesgo:** doble/triple acreditación por múltiples fuentes activas.

### 2.2 Canje de puntos
- `modulos/ventas.py` aún ejecuta `loyalty.canjear(...)` antes de confirmar la venta (pre-pago UI).
- Aunque existe `preview_redemption` y `compute_redemption_discount`, la UI todavía usa canje real en ese punto.

**Riesgo:** canje huérfano si falla la venta y descuento no transaccional con `venta_id`.

### 2.3 Eventos de venta
- `SalesService` publica `VENTA_COMPLETADA`.
- `ProcesarVentaUC` también publica `VENTA_COMPLETADA` (duplicidad potencial).

**Riesgo:** handlers post-venta ejecutados más de una vez (lealtad, sync, tesorería, etc.).

### 2.4 Inventario
- Ruta oficial: `SALE_ITEMS_PROCESS` + `SaleInventoryHandler` (dentro de SAVEPOINT).
- UI (`ventas.py`) todavía publica `AJUSTE_INVENTARIO` y `STOCK_ACTUALIZADO` al finalizar venta.

**Riesgo:** duplicidad de efectos de stock o acoplamiento UI→negocio.

### 2.5 Finanzas / Caja / Tesorería
- Ruta oficial de contado: `SaleFinanceHandler` en `SALE_ITEMS_PROCESS` (`register_income`).
- Crédito: `CreditSaleFinanceHandler` en `SALE_ITEMS_PROCESS` (CxC + asiento).
- `SalesService` aún contiene post-procesos financieros y asientos adicionales en algunos paths.
- `wiring.py` tesorería excluye diferidos con set literal (no helper centralizado de normalización).

**Riesgo:** duplicidad contable/caja y reglas divergentes por strings.

### 2.6 CxC
- Debe vivir en `CreditSaleFinanceHandler` durante `SALE_ITEMS_PROCESS`.
- Persisten rutas con validación/decisión en UI por string visible de forma de pago.

**Riesgo:** validaciones inconsistentes de crédito y posible ruta paralela.

### 2.7 MercadoPago
- UI puede ejecutar venta normal y luego generar link (`crear_link`).

**Riesgo:** venta marcada/contabilizada como completada antes de confirmación de pago.

### 2.8 Normalización de pago
- Existe normalización, pero hay comparaciones directas con strings visibles en UI/handlers (`"Crédito"`, `"Credito"`, `"Mercado Pago"`).

**Riesgo:** exclusiones/validaciones inconsistentes por acento, casing y variantes.

### 2.9 Tests débiles / falsos positivos
- Se detectan patrones `except Exception: pass` en áreas críticas, incluyendo flujo de ventas y servicios relacionados.
- Hay tests de no-duplicidad existentes, pero algunos aún validan de forma indirecta o por source-inspection.

**Riesgo:** regresiones silenciosas.

### 2.10 Folio duplicado conceptual
- `SalesService` mantiene `_generate_unique_sale_folio` en paralelo conceptual con folio generado en repositorio.

**Riesgo:** fuente duplicada de verdad del folio.

## 3) Archivos afectados prioritarios

1. `pos_spj_v13.4/modulos/ventas.py`
2. `pos_spj_v13.4/core/use_cases/venta.py`
3. `pos_spj_v13.4/core/services/sales_service.py`
4. `pos_spj_v13.4/core/services/loyalty_service.py`
5. `pos_spj_v13.4/core/services/payment_normalization.py`
6. `pos_spj_v13.4/core/events/wiring.py`
7. `pos_spj_v13.4/core/events/handlers/finance_handler.py`
8. `pos_spj_v13.4/core/events/handlers/inventory_handler.py`
9. `pos_spj_v13.4/repositories/ventas.py`
10. `pos_spj_v13.4/core/app_container.py`
11. `pos_spj_v13.4/tests/*` (suite de ventas/fidelidad/eventos)

## 4) Orden de corrección propuesto (confirmado)

1. Fase 1: normalización de forma de pago end-to-end.
2. Fase 2: acumulación de fidelidad en fuente única (`VENTA_COMPLETADA` handler idempotente).
3. Fase 3: canje transaccional (preview UI, apply backend post-venta).
4. Fase 4: limpiar `ProcesarVentaUC` de efectos duplicados.
5. Fase 5: reducir post-procesos de `SalesService` y centralizar en handlers.
6. Fase 6: retirar eventos de inventario de negocio desde UI.
7. Fase 7: flujo MercadoPago pendiente (sin `VENTA_COMPLETADA` hasta confirmación).
8. Fase 8: blindaje real de `VentaRepository` legacy.
9. Fase 9: tests reales sin `except/pass` y validación DB efectiva.
10. Fase 10: documentación oficial final.

## 5) Tests necesarios por fase (resumen)

- `tests/test_payment_method_normalization.py`
- `tests/test_loyalty_single_accrual.py`
- `tests/test_loyalty_redemption_transactional.py`
- `tests/test_procesar_venta_uc_no_duplicate_side_effects.py`
- `tests/test_sales_service_single_event_flow.py`
- `tests/test_ui_does_not_publish_inventory_business_events.py`
- `tests/test_mercado_pago_pending_flow.py`
- `tests/test_legacy_venta_repository_guardrail.py`
- `tests/test_sales_no_duplication_real.py`

## 6) Riesgos residuales antes de Fase 1

- Duplicidad de efectos por coexistencia UC + SalesService + wiring.
- Canje no transaccional desde UI.
- MercadoPago link aún tratado como venta normal en flujo actual.
- Legacy repository aún invocable sin guardrail fuerte.

---

## Evidencia técnica usada en esta auditoría

Se ejecutaron búsquedas globales y lectura dirigida de archivos para confirmar los puntos anteriores, sin modificar lógica de negocio en esta fase.

## Actualización de cierre (Fase 10)

Estado de fases:
- Fase 1 a Fase 9: implementadas.
- Fase 10: documentación de flujo oficial y hardening CI por dominio completados.

Riesgos cerrados respecto al diagnóstico inicial:
- Doble acreditación de fidelidad.
- Canje pre-pago desde UI.
- Publicación de eventos de inventario de negocio desde UI.
- Duplicidad de `VENTA_COMPLETADA` desde UC.
- Flujo MercadoPago sin separación pendiente/confirmado.
- Uso accidental de `VentaRepository` legacy sin guardrail.

Riesgos técnicos residuales:
- Deprecación `datetime.utcnow` en outbox (no bloqueante funcional).
- Falsos negativos en suite global por infraestructura cruzada UI/API (mitigado con CI segmentado).
