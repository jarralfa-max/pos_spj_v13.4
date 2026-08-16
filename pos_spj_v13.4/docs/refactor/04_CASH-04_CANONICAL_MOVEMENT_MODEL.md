# CASH-04 - FASE 4 modelo canonico de movimientos de Caja

Fecha: 2026-08-16

## Veredicto FASE 4

Estado: COMPLETA para el alcance del modelo canonico de movimientos de Caja.

Se consolidó el contrato de movimientos operativos para que el ledger siga
siendo inmutable y reconstruible, pero sin aceptar combinaciones ambiguas de
tipo/direccion ni movimientos de custodia sin documento origen.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Direccion canonica por tipo de movimiento | Cubierto |
| `Decimal` obligatorio para importes de dominio | Cubierto |
| `SAFE_DROP`, `CASH_PICKUP`, `CASH_HANDOVER`, ventas, reembolsos y apertura requieren documento origen | Cubierto |
| Reverso es movimiento compensatorio, no muta el original | Cubierto |
| `reversal_of_id` solo aplica a `REVERSAL` | Cubierto |
| `REVERSAL` requiere movimiento original | Cubierto |
| Alias legacy `HANDOVER` eliminado del catalogo de movimientos | Cubierto |
| Schema rechaza direccion incoherente | Cubierto |
| Schema rechaza `HANDOVER` como movimiento legacy | Cubierto |
| Safe drop queda enlazado a documento operativo para handover | Cubierto |

## Archivos modificados

- `backend/domain/cash_register/movement_model.py`
- `backend/domain/cash_register/entities.py`
- `backend/domain/cash_register/enums.py`
- `backend/application/cash_register/ledger_use_cases.py`
- `backend/application/cash_register/movement_use_cases.py`
- `migrations/standalone/175_cash_register_bounded_context_schema.py`
- `tests/unit/cash_register/test_cash_register_domain.py`
- `tests/integration/cash_register/test_cash_ledger_flow.py`
- `tests/integration/cash_register/test_cash_register_schema_born_clean.py`
- `tests/integration/cash_register/test_cash_register_unit_of_work.py`
- `tests/integration/cash_register/test_cash_overview_query_service.py`
- `tests/architecture/test_cash_ledger_is_canonical.py`

## Evidencia ejecutada

```text
python -m unittest tests.unit.cash_register.test_cash_register_domain tests.integration.cash_register.test_cash_ledger_flow tests.integration.cash_register.test_cash_register_schema_born_clean tests.architecture.test_cash_ledger_is_canonical -v
Ran 28 tests
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
python -m py_compile backend\domain\cash_register\movement_model.py backend\domain\cash_register\entities.py backend\domain\cash_register\enums.py backend\application\cash_register\ledger_use_cases.py backend\application\cash_register\movement_use_cases.py migrations\standalone\175_cash_register_bounded_context_schema.py tests\unit\cash_register\test_cash_register_domain.py tests\integration\cash_register\test_cash_register_schema_born_clean.py tests\integration\cash_register\test_cash_register_unit_of_work.py tests\integration\cash_register\test_cash_overview_query_service.py tests\architecture\test_cash_ledger_is_canonical.py
OK
```

## Deuda fuera de FASE 4

1. CASH-25 mantiene el burn-down final de rutas y tablas legacy externas al
   modelo canonico.
2. CASH-26 mantiene la validacion CI completa y bootstrap end-to-end.
