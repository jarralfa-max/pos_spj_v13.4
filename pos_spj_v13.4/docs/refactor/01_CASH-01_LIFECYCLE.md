# CASH-01 - FASE 1 seguridad base y lifecycle canonico de Caja

Fecha: 2026-08-16  
HEAD base auditado: `a2742e12c62b00c661f84e3081dbdfca95ed5c09`

## Veredicto FASE 1

Estado: COMPLETA para el alcance de FASE 1.

Se centralizo la tabla canonica de transiciones de `CashShift` en dominio y se conecto desde el agregado y desde los use cases de turno. La seguridad base queda protegida por permisos `CAJA.accion`, checker fail-closed, role matrix, capability resolver y paridad UI/backend.

La deuda legacy fuera de la ruta canonica no bloquea FASE 1 y queda expresamente diferida a CASH-25 / eliminacion legacy. La formalizacion posterior de resolucion operacional avanzada queda para la siguiente fase, sin duplicar la politica de lifecycle.

## Lifecycle canonico actual

Estados existentes preservados:

```text
OPENING
OPEN
SUSPENDED
PENDING_COUNT
COUNTING
COUNTED
PENDING_REVIEW
CLOSING
CLOSED
FORCE_CLOSED
CANCELLED
```

Transiciones operativas explicitadas en `CashShiftLifecyclePolicy`:

```text
OPEN      -> SUSPENDED
SUSPENDED -> OPEN
OPEN      -> CLOSING
CLOSING   -> CLOSED
```

Estados activos/incompatibles para concurrencia:

```text
OPENING
OPEN
SUSPENDED
PENDING_COUNT
COUNTING
COUNTED
PENDING_REVIEW
CLOSING
```

Estados finales:

```text
CLOSED
FORCE_CLOSED
CANCELLED
```

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| No transicionar desde estado final | Cubierto por `CashShiftLifecyclePolicy.ensure_transition` |
| Suspender requiere turno `OPEN` y motivo | Cubierto por policy + agregado/use case |
| Reanudar requiere `SUSPENDED` | Cubierto por policy + agregado/use case |
| Pre-cierre requiere `OPEN` | Cubierto por policy + agregado/use case |
| Cierre final requiere `CLOSING` + Corte Z final | Cubierto por policy + agregado |
| Movimiento/safe drop requiere turno operable `OPEN` | Cubierto por `ensure_operable` en ledger/safe drop |
| Un turno activo por caja/cajon/terminal/cajero | Cubierto por constraints DB + validacion de apertura |
| Corte X no cierra | Cubierto por dominio/tests existentes |
| Corte Z cierra y es unico | Cubierto por policy de cierre + constraints/tests existentes |
| Transiciones de turno sin strings dispersos en comandos | Cubierto por guardrail de arquitectura |
| Permisos `CAJA.accion` sin `CASH_*` runtime | Cubierto por tests de seguridad |
| Role matrix sin mutaciones inferidas desde VIEW | Cubierto por tests unitarios |
| Capabilities UI == permisos backend | Cubierto por test de paridad |

## Archivos modificados

- `backend/domain/cash_register/policies/workflow_policies.py`
- `backend/domain/cash_register/entities.py`
- `backend/application/cash_register/shift_use_cases.py`
- `backend/application/cash_register/ledger_use_cases.py`
- `backend/application/cash_register/movement_use_cases.py`
- `backend/infrastructure/db/repositories/cash_register/repositories.py`
- `backend/infrastructure/desktop/cash_register_factory.py`
- `frontend/desktop/modules/cash_register/cash_register_routes.py`
- `tests/unit/cash_register/test_cash_register_domain.py`
- `tests/architecture/test_cash_register_domain_contract.py`
- `tests/architecture/test_cash_shift_use_cases_are_canonical.py`
- `tests/architecture/test_cash_difference_ui_wiring.py`
- `tests/architecture/test_cash_handover_ui_wiring.py`
- `tests/architecture/test_cash_x_cut_ui_wiring.py`
- `tests/architecture/test_cash_z_cut_ui_wiring.py`

## Evidencia ejecutada

```text
python -m unittest discover tests\unit\cash_register -v
Ran 90 tests
OK
```

```text
python -m unittest tests.unit.cash_register.test_cash_register_domain tests.integration.cash_register.test_cash_shift_lifecycle tests.architecture.test_cash_shift_use_cases_are_canonical tests.architecture.test_cash_register_domain_contract -v
Ran 23 tests
OK
```

```text
python -m unittest tests.unit.cash_register.test_cash_register_security tests.unit.cash_register.test_cash_register_role_matrix tests.architecture.test_cash_register_security_foundation tests.architecture.test_cash_register_permissions_catalog -v
Ran 17 tests
OK
```

```text
python -m unittest discover tests\integration\cash_register -v
Ran 86 tests
OK
```

```text
python -m unittest discover tests\architecture -p "test_cash*.py" -v
Ran 88 tests
OK
```

## Deuda transferida fuera de FASE 1

1. Migrar/eliminar consumidores legacy que aun usan `turnos_caja/movimientos_caja` en CASH-25.
2. Formalizar resolucion operacional avanzada en la siguiente fase sin introducir service locator.
3. Revisar si `PENDING_COUNT`, `COUNTING`, `COUNTED`, `PENDING_REVIEW` deben tener transiciones de application use cases explicitas al cerrar conteo/cierre.
