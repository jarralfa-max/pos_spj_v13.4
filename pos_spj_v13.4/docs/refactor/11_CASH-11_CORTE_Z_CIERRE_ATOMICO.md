# FASE 11 — CORTE Z Y CIERRE ATÓMICO

Fecha: 2026-08-15

## Estado

✅ COMPLETA en el alcance de la fase.

## Objetivo

Cerrar la brecha de Corte Z final: el documento debe consolidar conteo,
diferencia, cierre de turno, eventos y outbox en una frontera atómica, sin
filtrar importes sensibles por la ruta de consulta/UI/impresión.

## Cambios aplicados

- `GenerateZCutUseCase` se preserva como frontera transaccional única:
  - valida turno en `CLOSING`;
  - rechaza safe drops pendientes;
  - exige conteo ciego confirmado;
  - calcula esperado desde ledger reconstruible;
  - crea diferencia dentro de la misma UoW;
  - cierra turno;
  - registra evento y outbox en la misma transacción.
- `CashZCutQueryService` ahora separa:
  - permiso de documento: `CAJA.corte_z.ver`;
  - permiso de importes sensibles: `CAJA.ver.importes_sensibles`.
- La proyección de Corte Z redacta:
  - efectivo esperado;
  - efectivo contado;
  - diferencia;
  - snapshot;
  cuando el actor solo tiene permiso de ver Corte Z.
- La UI de Corte Z muestra `Restringido` en columnas/KPI sensibles cuando no
  existe permiso de importes sensibles.
- La impresión/reimpresión de Corte Z valida primero el permiso específico
  `CAJA.corte_z.imprimir`/`CAJA.corte_z.reimprimir` antes de construir el
  documento.
- El documento de impresión de Corte Z no fabrica totales cuando la consulta
  devuelve importes redactados.

## Archivos modificados

- `backend/application/cash_register/z_cut_query_service.py`
- `backend/infrastructure/desktop/cash_register_factory.py`
- `frontend/desktop/modules/cash_register/cash_z_cuts_page.py`
- `tests/unit/cash_register/test_cash_z_cut_query_service.py`
- `tests/integration/cash_register/test_z_cut_finalization_flow.py`

## Evidencia de pruebas

```text
python -m unittest tests.unit.cash_register.test_cash_z_cut_query_service tests.integration.cash_register.test_z_cut_finalization_flow tests.architecture.test_cash_z_cut_ui_wiring tests.unit.cash_register.test_cash_register_presenter_context tests.unit.cash_register.test_cash_printing tests.integration.cash_register.test_cash_print_repository -v
Ran 38 tests in 0.444s
OK

python -m unittest discover tests\unit\cash_register
Ran 92 tests in 0.569s
OK

python -m unittest discover tests\integration\cash_register
Ran 93 tests in 3.163s
OK

python -m unittest discover tests\architecture -p "test_cash*.py"
Ran 92 tests in 2.511s
OK

python -m unittest discover tests\e2e -p "*cash*.py"
Ran 11 tests in 0.240s
OK
```

## Riesgos cubiertos

- Fuga de efectivo esperado/contado/diferencia con solo permiso VIEW.
- Consulta de documento para imprimir antes de validar permiso de impresión.
- Regresión del cierre atómico de turno/diferencia/evento/outbox.
- Regresión de impresión/reimpresión post-commit.

## Veredicto

NO LISTO PARA MERGE global.

FASE 11 queda cerrada, pero el bounded context completo de Caja todavía depende
de las fases posteriores y de la validación final.
