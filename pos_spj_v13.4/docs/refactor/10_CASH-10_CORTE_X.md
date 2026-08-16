# CASH-10 - FASE 10 Corte X

Fecha: 2026-08-16

## Veredicto FASE 10

Estado: COMPLETA para el alcance de Corte X: documento parcial, snapshot
inmutable, permisos, visibilidad, impresion, reimpresion y auditoria.

Corte X no cierra ni reinicia turno. Genera un snapshot operativo del ledger
actual, respeta visibilidad de importes sensibles y queda bloqueado mientras
existe conteo ciego abierto para evitar fugas del efectivo esperado. La
impresion/reimpresion usa la cola canonica de documentos de Caja; el motivo de
reimpresion queda persistido en auditoria, evento y metadata del job.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Generar Corte X requiere `CAJA.corte_x.generar` | Cubierto |
| Ver Corte X requiere `CAJA.corte_x.ver` | Cubierto |
| Importes sensibles requieren `CAJA.ver.importes_sensibles` | Cubierto |
| Corte X no cierra ni reinicia el turno | Cubierto |
| Snapshot es inmutable despues de generado | Cubierto |
| Idempotencia por `operation_id` | Cubierto |
| Bloqueo durante conteo ciego abierto | Cubierto |
| Query redacted durante conteo ciego abierto | Cubierto |
| Impresion requiere permiso especifico | Cubierto |
| Reimpresion requiere original y motivo | Cubierto |
| Reimpresion no duplica documento original | Cubierto |
| Motivo de reimpresion queda en auditoria/evento/job | Cubierto |
| Fallo de impresion no declara exito falso | Cubierto |
| UI conecta pagina -> presenter -> factory -> use case | Cubierto |

## Archivos modificados

- `backend/application/cash_register/printing.py`
- `tests/unit/cash_register/test_cash_printing.py`
- `tests/integration/cash_register/test_cash_print_repository.py`

## Rutas verificadas sin cambio requerido

- `backend/application/cash_register/x_cut_use_cases.py`
- `backend/application/cash_register/x_cut_query_service.py`
- `frontend/desktop/modules/cash_register/cash_x_cuts_page.py`
- `frontend/desktop/modules/cash_register/cash_register_presenter.py`
- `backend/infrastructure/desktop/cash_register_factory.py`
- `tests/integration/cash_register/test_x_cut_document_flow.py`
- `tests/architecture/test_cash_x_cut_ui_wiring.py`
- `tests/architecture/test_cash_printing_boundary.py`

## Evidencia ejecutada

```text
python -m unittest tests.integration.cash_register.test_x_cut_document_flow tests.unit.cash_register.test_cash_printing tests.integration.cash_register.test_cash_print_repository tests.architecture.test_cash_x_cut_ui_wiring tests.architecture.test_cash_printing_boundary tests.unit.cash_register.test_cash_register_presenter_context -v
Ran 36 tests
OK
```

```text
python -m unittest discover tests\integration\cash_register
Ran 92 tests
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
python -m py_compile backend\application\cash_register\printing.py tests\unit\cash_register\test_cash_printing.py tests\integration\cash_register\test_cash_print_repository.py
OK
```

## Deuda fuera de FASE 10

1. CASH-25 mantiene eliminacion final de legacy externo.
2. CASH-26 mantiene validacion CI completa y bootstrap/integridad global.
