# CASH-09 - FASE 9 diferencias

Fecha: 2026-08-16

## Veredicto FASE 9

Estado: COMPLETA para el alcance de diferencias: deteccion desde Corte Z,
clasificacion por tolerancias, reincidencia, alertas, explicacion por
responsable, revision independiente, resolucion independiente, UI real y
eventos auditables.

La diferencia no se elimina aunque este dentro de tolerancia; la tolerancia
decide el workflow/severidad, no la existencia del registro. La explicacion
queda restringida al responsable asignado por el turno/cajero, y revision y
resolucion exigen actores distintos segun segregacion de funciones.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Corte Z crea diferencia cuando contado != esperado | Cubierto |
| Diferencia se persiste aunque este dentro de tolerancia | Cubierto |
| Clasificacion SHORTAGE/OVERAGE por signo | Cubierto |
| Tolerancia decide severidad/workflow, no existencia | Cubierto |
| Umbral critico y reincidencia elevan severidad | Cubierto |
| Reincidencia esta acotada por sucursal y responsable | Cubierto |
| Alerta/WhatsApp se publica como evento, no desde Qt | Cubierto |
| Explicacion requiere `CAJA.diferencia.explicar` | Cubierto |
| Explicacion debe registrarla el responsable de la diferencia | Cubierto |
| Revision requiere `CAJA.diferencia.revisar` | Cubierto |
| Revisor no puede ser detector ni explicador | Cubierto |
| Resolucion requiere `CAJA.diferencia.resolver` | Cubierto |
| Resolutor no puede ser detector, explicador ni revisor | Cubierto |
| Transiciones son idempotentes por `operation_id` | Cubierto |
| UI conecta pagina -> dialogo -> presenter -> use case | Cubierto |

## Archivos modificados

- `backend/application/cash_register/difference_use_cases.py`
- `tests/integration/cash_register/test_cash_difference_workflow.py`

## Rutas verificadas sin cambio requerido

- `backend/application/cash_register/difference_query_service.py`
- `backend/application/cash_register/z_cut_use_cases.py`
- `backend/domain/cash_register/difference_policy.py`
- `frontend/desktop/modules/cash_register/cash_differences_page.py`
- `frontend/desktop/modules/cash_register/cash_register_presenter.py`
- `backend/infrastructure/desktop/cash_register_factory.py`
- `tests/unit/cash_register/test_cash_difference_policy.py`
- `tests/unit/cash_register/test_cash_difference_query_service.py`
- `tests/architecture/test_cash_difference_alert_boundary.py`
- `tests/architecture/test_cash_difference_ui_wiring.py`

## Evidencia ejecutada

```text
python -m unittest tests.integration.cash_register.test_cash_difference_workflow tests.unit.cash_register.test_cash_difference_policy tests.unit.cash_register.test_cash_difference_query_service tests.architecture.test_cash_difference_alert_boundary tests.architecture.test_cash_difference_ui_wiring tests.integration.cash_register.test_z_cut_finalization_flow tests.unit.cash_register.test_cash_register_presenter_context -v
Ran 32 tests
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
python -m py_compile backend\application\cash_register\difference_use_cases.py tests\integration\cash_register\test_cash_difference_workflow.py
OK
```

## Deuda fuera de FASE 9

1. CASH-25 mantiene eliminacion final de legacy externo.
2. CASH-26 mantiene validacion CI completa y bootstrap/integridad global.
