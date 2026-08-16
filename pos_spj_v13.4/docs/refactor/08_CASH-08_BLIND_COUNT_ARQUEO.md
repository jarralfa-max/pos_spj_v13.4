# CASH-08 - FASE 8 conteo ciego / arqueo

Fecha: 2026-08-16

## Veredicto FASE 8

Estado: COMPLETA para el alcance de conteo ciego, captura por denominaciones,
bloqueo de conteo y proteccion del efectivo esperado durante arqueo abierto.

El flujo canonico conserva el esperado oculto hasta que el conteo este
confirmado y el actor tenga permiso explicito para revelarlo. Ademas, las rutas
laterales que podian exponer el esperado durante un conteo abierto ahora quedan
protegidas: dashboard, listado de turnos y Corte X.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Iniciar conteo requiere permiso `CAJA.conteo.iniciar` | Cubierto |
| Captura por denominaciones vigentes del catalogo | Cubierto |
| Cantidades enteras no negativas | Cubierto |
| El esperado no se consulta ni se emite durante conteo abierto | Cubierto |
| Una sola sesion abierta por turno | Cubierto |
| Confirmar bloquea captura posterior | Cubierto |
| Revelar esperado exige conteo confirmado | Cubierto |
| Revelar esperado exige `CAJA.conteo.ver_esperado` | Cubierto |
| Dashboard oculta efectivo esperado mientras hay arqueo abierto | Cubierto |
| Turnos ocultan efectivo esperado mientras hay arqueo abierto | Cubierto |
| Corte X redacted mientras hay arqueo abierto | Cubierto |
| Generar/imprimir Corte X queda bloqueado durante arqueo abierto | Cubierto |
| Idempotencia de captura y confirmacion | Cubierto |
| Eventos de conteo no filtran importe esperado | Cubierto |

## Archivos creados

- `backend/application/cash_register/blind_count_visibility.py`

## Archivos modificados

- `backend/application/cash_register/overview_query_service.py`
- `backend/application/cash_register/shift_query_service.py`
- `backend/application/cash_register/x_cut_query_service.py`
- `backend/application/cash_register/x_cut_use_cases.py`
- `frontend/desktop/modules/cash_register/cash_shifts_page.py`
- `tests/integration/cash_register/test_cash_overview_query_service.py`
- `tests/integration/cash_register/test_cash_shift_lifecycle.py`
- `tests/integration/cash_register/test_x_cut_document_flow.py`

## Rutas verificadas sin cambio requerido

- `backend/application/cash_register/blind_count_use_cases.py`
- `backend/application/cash_register/blind_count_query_service.py`
- `frontend/desktop/modules/cash_register/blind_count_page.py`
- `frontend/desktop/modules/cash_register/cash_register_presenter.py`
- `tests/integration/cash_register/test_blind_cash_count_flow.py`

## Evidencia ejecutada

```text
python -m unittest tests.integration.cash_register.test_blind_cash_count_flow tests.integration.cash_register.test_cash_shift_lifecycle tests.integration.cash_register.test_cash_overview_query_service tests.integration.cash_register.test_x_cut_document_flow tests.unit.cash_register.test_cash_register_presenter_context tests.architecture.test_cash_x_cut_ui_wiring -v
Ran 38 tests
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
python -m py_compile backend\application\cash_register\blind_count_visibility.py backend\application\cash_register\overview_query_service.py backend\application\cash_register\shift_query_service.py backend\application\cash_register\x_cut_query_service.py backend\application\cash_register\x_cut_use_cases.py frontend\desktop\modules\cash_register\cash_shifts_page.py tests\integration\cash_register\test_blind_cash_count_flow.py tests\integration\cash_register\test_cash_shift_lifecycle.py tests\integration\cash_register\test_cash_overview_query_service.py tests\integration\cash_register\test_x_cut_document_flow.py
OK
```

## Deuda fuera de FASE 8

1. CASH-25 mantiene eliminacion final de legacy externo.
2. CASH-26 mantiene validacion CI completa y bootstrap/integridad global.
