# CASH-03 - FASE 3 esquema born-clean de Caja

Fecha: 2026-08-16  
HEAD base auditado: `a2742e12c62b00c661f84e3081dbdfca95ed5c09`

## Veredicto FASE 3

Estado: COMPLETA para el alcance de CASH-3.

Se valido y reforzo el esquema canonico de Caja para nacer limpio desde
migraciones, sin rescate legacy, con UUIDv7 como identidad, dinero persistido
como texto decimal, constraints operativas, indices, idempotencia y bootstrap
repetible.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Tablas canonicas creadas desde migraciones | Cubierto |
| Sin `AUTOINCREMENT` en tablas de Caja | Cubierto |
| Sin `REAL` para dinero de Caja | Cubierto |
| IDs `TEXT` con constraint UUIDv7 lowercase | Cubierto |
| `operation_id` unico por operacion idempotente | Cubierto |
| Un turno activo por caja/cajon/terminal/cajero | Cubierto por indices parciales |
| Un Corte Z final por turno | Cubierto por indice unico parcial |
| Constraints de estados de turno, conteo, cortes, diferencias, entrega, reembolso, impresion y sync | Cubierto |
| `PRAGMA foreign_key_check` limpio | Cubierto |
| `PRAGMA integrity_check = ok` | Cubierto |
| Bootstrap idempotente sin defaults de negocio | Cubierto |
| Perfil de permisos acepta `CAJA.accion` y rechaza `CASH_*` | Cubierto |
| Sin dual-write/legacy rescue en migracion base | Cubierto |

## Archivos modificados

- `migrations/standalone/176_cash_register_configuration_schema.py`
- `tests/integration/cash_register/test_cash_register_schema_born_clean.py`
- `tests/integration/cash_register/test_cash_register_configuration_schema.py`
- `tests/architecture/test_cash_register_schema_lives_in_migrations.py`

## Evidencia ejecutada

```text
python -m unittest tests.integration.cash_register.test_cash_register_schema_born_clean tests.integration.cash_register.test_cash_register_configuration_schema tests.architecture.test_cash_register_schema_lives_in_migrations -v
Ran 14 tests
OK
```

```text
python -m unittest discover tests\unit\cash_register
Ran 90 tests
OK
```

```text
python -m unittest discover tests\integration\cash_register
Ran 87 tests
OK
```

```text
python -m unittest discover tests\architecture -p "test_cash*.py"
Ran 91 tests
OK
```

```text
python -m py_compile migrations\standalone\176_cash_register_configuration_schema.py tests\integration\cash_register\test_cash_register_schema_born_clean.py tests\integration\cash_register\test_cash_register_configuration_schema.py tests\architecture\test_cash_register_schema_lives_in_migrations.py
OK
```

## Deuda fuera de FASE 3

1. El burn-down final de rutas/tablas legacy ajenas al esquema born-clean se
   mantiene en CASH-25.
2. La validacion CI completa y bootstrap end-to-end quedan para CASH-26.
