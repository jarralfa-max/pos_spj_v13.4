# CASH-02 - FASE 2 contexto operacional explicito de Caja

Fecha: 2026-08-16  
HEAD base auditado: `a2742e12c62b00c661f84e3081dbdfca95ed5c09`

## Veredicto FASE 2

Estado: COMPLETA para el alcance de FASE 2.

Se formalizo un resolver explicito de contexto operacional para Caja. El
frontend no recibe `AppContainer`, no busca servicios por su cuenta y no fabrica
identidades para caja, cajon, terminal, turno o dispositivo de sincronizacion.

El factory de escritorio actua como composition root: construye el resolver con
`connection`, `session` y `composition_root`, y entrega callbacks explicitos al
`CashRegisterPresenter`.

## Invariantes cubiertas

| Invariante | Estado |
| --- | --- |
| Presenter recibe contexto por callbacks explicitos | Cubierto |
| Factory delega resolucion a `DesktopCashOperationalContextResolver` | Cubierto |
| Resolver usa tablas canonicas `cash_registers`, `cash_drawers`, `pos_terminals`, `cash_shifts` | Cubierto |
| Turno activo usa `CashShiftLifecyclePolicy.ACTIVE_STATUSES` | Cubierto |
| No se fabrican IDs `admin`, `desktop`, `system`, `MAIN`, `1` | Cubierto |
| Sin `new_uuid`/`uuid.uuid4` para contexto activo | Cubierto |
| Si hay turno activo persistido, manda sobre defaults de caja/cajon/terminal | Cubierto |
| Si falta dispositivo de sync, usa terminal activa canonica | Cubierto |
| Si falta contexto requerido, presenter falla explicitamente | Cubierto |

## Archivos creados

- `backend/infrastructure/desktop/cash_operational_context.py`
- `tests/architecture/test_cash_operational_context_resolver.py`

## Archivos modificados

- `backend/infrastructure/desktop/cash_register_factory.py`
- `tests/architecture/test_cash_app_container_born_clean_wiring.py`

## Evidencia ejecutada

```text
python -m unittest tests.integration.cash_register.test_cash_register_factory_active_context tests.unit.cash_register.test_cash_register_presenter_context tests.architecture.test_cash_operational_context_resolver -v
Ran 23 tests
OK
```

```text
python -m unittest discover tests\unit\cash_register -v
Ran 90 tests
OK
```

```text
python -m unittest discover tests\integration\cash_register -v
Ran 86 tests
OK
```

```text
python -m unittest discover tests\architecture -p "test_cash*.py" -v
Ran 90 tests
OK
```

## Pendiente fuera de FASE 2

1. Mantener eliminacion legacy en CASH-25.
2. Validar bootstrap limpio y CI completa en CASH-26.
3. Si se requiere multi-terminal concurrente avanzado, ampliar el resolver con
   una politica de asignacion explicita sin reintroducir service locator.
