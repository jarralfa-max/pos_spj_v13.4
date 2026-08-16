# CASH-07 - FASE 7 retiros, ingresos, safe drop y entrega de valores

Fecha: 2026-08-16

## Veredicto FASE 7

Estado: COMPLETA para el alcance de movimientos manuales, retiros, safe drop
y entrega de valores.

Caja registra ingresos y retiros como movimientos inmutables del ledger. Los
retiros y safe drops se validan contra el saldo reconstruido del turno, sin
corregir acumulados ni permitir efectivo negativo. Safe drop permanece como
cambio de custodia, no como gasto, y su entrega a Tesoreria exige preparacion
con denominaciones, doble confirmacion, segregacion de funciones, recepcion y
disputa auditada.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Ingresos manuales requieren permiso especifico | Cubierto |
| Retiros manuales requieren permiso especifico | Cubierto |
| Safe drop requiere permiso especifico y catalogo de motivo | Cubierto |
| Retiros y safe drops no exceden efectivo reconstruido | Cubierto |
| Ledger permanece inmutable y reconstruible | Cubierto |
| Limites monetarios exigen autorizacion en caliente | Cubierto |
| Autorizador debe ser actor independiente cuando aplica | Cubierto |
| Safe drop crea salida de caja y cambio de custodia | Cubierto |
| Una salida safe drop no puede preparar dos entregas | Cubierto |
| Preparacion de entrega exige denominaciones exactas | Cubierto |
| Entrega y recepcion son idempotentes por operacion | Cubierto |
| Receptor no puede ser quien entrega | Cubierto |
| Diferencia en recepcion abre disputa y bloquea transferencia limpia | Cubierto |
| Disputa manual exige motivo y queda auditada | Cubierto |
| UI real conecta pagina -> dialogo -> presenter -> use case | Cubierto |

## Archivos modificados

- `backend/application/cash_register/ledger_use_cases.py`
- `tests/integration/cash_register/test_cash_ledger_flow.py`

## Rutas verificadas sin cambio requerido

- `backend/application/cash_register/movement_use_cases.py`
- `backend/infrastructure/desktop/cash_register_factory.py`
- `frontend/desktop/modules/cash_register/cash_ledger_page.py`
- `frontend/desktop/modules/cash_register/cash_handovers_page.py`
- `frontend/desktop/modules/cash_register/cash_register_presenter.py`
- `tests/integration/cash_register/test_cash_safe_drop_handover.py`
- `tests/integration/cash_register/test_cash_value_handover_flow.py`
- `tests/unit/cash_register/test_cash_register_presenter_context.py`
- `tests/architecture/test_cash_handover_ui_wiring.py`

## Evidencia ejecutada

```text
python -m unittest tests.integration.cash_register.test_cash_ledger_flow tests.integration.cash_register.test_cash_safe_drop_handover tests.integration.cash_register.test_cash_value_handover_flow tests.unit.cash_register.test_cash_register_presenter_context tests.architecture.test_cash_handover_ui_wiring -v
Ran 33 tests
OK
```

```text
python -m unittest discover tests\integration\cash_register
Ran 89 tests
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
python -m py_compile backend\application\cash_register\ledger_use_cases.py tests\integration\cash_register\test_cash_ledger_flow.py
OK
```

## Deuda fuera de FASE 7

1. CASH-25 mantiene el burn-down final de legacy externo.
2. CASH-26 mantiene validacion CI completa y bootstrap/integridad global.
