# CASH-05 - FASE 5 integracion Ventas -> Caja

Fecha: 2026-08-16

## Veredicto FASE 5

Estado: COMPLETA para el alcance de integracion operacional Ventas -> Caja.

Caja consume el evento canonico `SALE_COMPLETED` desde Ventas, registra
`PaymentRecord` y `PaymentAllocation`, exige turno abierto y registra en ledger
solamente el efecto fisico neto de efectivo. Ventas no escribe el ledger de
Caja y Caja no escribe tablas de Ventas.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Turno abierto obligatorio para ventas con y sin efectivo | Cubierto |
| `SUM(payment allocations) == total confirmado por Ventas` | Cubierto |
| Cambio reduce solo el efectivo fisico del cajon | Cubierto |
| Pago mixto registra liquidacion completa y solo efectivo impacta ledger | Cubierto |
| Tarjeta/transferencia/puntos/cupones/vales/saldo a favor no afectan cajon | Cubierto |
| Instrumentos comerciales requieren referencia/contrato validado externo | Cubierto |
| Idempotencia por evento de venta | Cubierto |
| Cancelacion/reverso compensa sin mutar movimiento original | Cubierto |
| Caja no importa servicios legacy de Ventas ni escribe tablas de Ventas | Cubierto |

## Archivos modificados

- `backend/application/cash_register/sales_integration.py`
- `backend/application/event_handlers/cash_register/sales_cash_handlers.py`
- `tests/e2e/test_cash_sales_integration.py`

## Evidencia ejecutada

```text
python -m unittest tests.e2e.test_cash_sales_integration tests.integration.cash_register.test_cash_commercial_instruments tests.integration.cash_register.test_cash_refund_factory_wiring tests.e2e.test_cash_sale_refund_flow -v
Ran 20 tests
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
Ran 10 tests
OK
```

```text
python -m py_compile backend\application\cash_register\sales_integration.py backend\application\event_handlers\cash_register\sales_cash_handlers.py tests\e2e\test_cash_sales_integration.py tests\unit\test_sales_application_refactor.py backend\application\services\sales_application_service.py
OK
```

## Limitacion del entorno

`python -m pytest tests\unit\test_sales_application_refactor.py -q` no pudo
ejecutarse porque el entorno actual no tiene instalado `pytest`.

## Deuda fuera de FASE 5

1. El evento especifico de `PaymentRecord`/settlement para outbox separado
   requiere revisar primero la restriccion actual `cash_outbox.operation_id
   UNIQUE`, para no duplicar side effects por una misma operacion de venta.
2. CASH-25 mantiene el burn-down final de rutas legacy externas.
3. CASH-26 mantiene la validacion CI completa.
