# CASH-06 - FASE 6 refunds/devoluciones -> Caja

Fecha: 2026-08-16

## Veredicto FASE 6

Estado: COMPLETA para el alcance de devoluciones monetarias hacia Caja.

Ventas conserva la autorizacion comercial de la devolucion. Caja ejecuta y
audita solamente la compensacion monetaria/operativa autorizada: valida metodo
original, autorizacion independiente, limites, efectivo disponible, salida
fisica del cajon cuando aplica y publica hechos para Finanzas/Fidelidad sin
mutar sus tablas.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Reembolso requiere autorizacion independiente | Cubierto |
| Reembolso exige turno abierto | Cubierto |
| Reembolso respeta metodo original | Cubierto |
| Efectivo reembolsado no excede efectivo original acumulado | Cubierto |
| Efectivo reembolsado no excede efectivo reconstruido en cajon | Cubierto |
| Reembolso CASH crea movimiento `CASH_REFUND` OUTFLOW | Cubierto |
| Reembolso no-cash no crea movimiento fisico | Cubierto |
| Todo reembolso crea `cash_refund_executions` | Cubierto |
| Instrumentos comerciales requieren contrato/referencia validada externa | Cubierto |
| Eventos incluyen frontera Finanzas/Fidelidad | Cubierto |
| Caja no muta Ventas, Inventario, Finanzas ni Fidelidad | Cubierto |
| Idempotencia por `operation_id` | Cubierto |

## Archivos modificados

- `backend/application/cash_register/refund_integration.py`
- `backend/application/cash_register/sales_integration.py`
- `backend/application/event_handlers/cash_register/sales_cash_handlers.py`
- `tests/e2e/test_cash_sale_refund_flow.py`
- `tests/integration/cash_register/test_cash_refund_factory_wiring.py`
- `tests/architecture/test_cash_refund_domain_boundaries.py`

## Evidencia ejecutada

```text
python -m unittest tests.e2e.test_cash_sale_refund_flow tests.integration.cash_register.test_cash_refund_factory_wiring tests.architecture.test_cash_refund_domain_boundaries -v
Ran 9 tests
OK
```

```text
python -m unittest discover tests\integration\cash_register
Ran 88 tests
OK
```

```text
python -m unittest discover tests\unit\cash_register
Ran 91 tests
OK
```

```text
python -m unittest discover tests\architecture -p "test_cash*.py"
Ran 92 tests
OK
```

```text
python -m unittest discover tests\e2e -p "*cash*.py"
Ran 11 tests
OK
```

```text
python -m py_compile backend\application\cash_register\refund_integration.py backend\application\cash_register\sales_integration.py backend\application\event_handlers\cash_register\sales_cash_handlers.py tests\e2e\test_cash_sale_refund_flow.py tests\integration\cash_register\test_cash_refund_factory_wiring.py tests\architecture\test_cash_refund_domain_boundaries.py
OK
```

## Deuda fuera de FASE 6

1. La devolucion fisica de mercancia sigue perteneciendo a Inventario/Ventas; Caja
   solo ejecuta compensacion monetaria.
2. CASH-25 mantiene el burn-down final de legacy externo.
3. CASH-26 mantiene validacion CI completa.
