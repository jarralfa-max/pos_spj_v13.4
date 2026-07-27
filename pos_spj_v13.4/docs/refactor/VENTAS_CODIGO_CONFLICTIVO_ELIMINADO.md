# VENTAS — Código conflictivo eliminado (FASE 8)

Fecha: 2026-05-28

## Eliminado/Reemplazado

1. `modulos/ventas.py::generar_ticket(...)`
- **Motivo:** reconstruía ticket desde `self.compra_actual` y `self.totales` después de venta.
- **Reemplazo:** `_aplicar_resultado_venta(...)` consume `result.ticket_payload`, `result.total` y `result.payment_breakdown`.
- **Cobertura:** `test_no_ticket_from_compra_actual_postventa`.

2. `modulos/ventas.py::_procesar_venta_via_uc(...)`
- **Motivo:** ruta legacy duplicada con `monto_pagado` basado en `self.totales['total_final']`.
- **Reemplazo:** flujo canónico `finalizar_venta(...)` + worker/factory + `ProcesarVentaUC`.
- **Cobertura:** `test_no_false_print_fallback`.

3. Reimpresión con `venta_id` incorrecto
- **Motivo:** payload de reimpresión usaba `venta_id=folio`.
- **Reemplazo:** `venta_id=int(vid)` en `_reimprimir_ultima_venta`.
- **Cobertura:** `test_no_venta_id_equals_folio_in_ticket_payload`.

4. Cálculo legacy de puntos en UI
- **Motivo:** estructuras locales tipo `puntos_resultado` desacopladas de backend.
- **Reemplazo:** lectura de `result.loyalty_result` con fallback controlado.
- **Cobertura:** `test_no_ui_final_points_calculation`.
