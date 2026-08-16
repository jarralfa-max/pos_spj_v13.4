# FASE 12 — CONFIGURACIÓN ENTERPRISE TIPADA

Fecha: 2026-08-15

## Estado

✅ COMPLETA en el alcance de la fase.

## Objetivo

Convertir la configuración de Caja en una ruta enterprise tipada, evitando que
catálogos críticos entren al backend únicamente como `section/name/value`.

## Cambios aplicados

- Se agregó una ruta canónica `execute_typed()` en `ConfigureCashRegisterUseCase`.
- Se introdujeron comandos tipados para:
  - ajustes jerárquicos/vigencias;
  - denominaciones;
  - medios de pago;
  - límites operativos;
  - reglas de alerta.
- Se agregó `CashConfigurationScope` para validar alcances:
  - `SYSTEM`;
  - `COMPANY`;
  - `BRANCH`;
  - `REGISTER`;
  - `USER`.
- La validación de configuración reutiliza entidades/value objects del dominio:
  - `CashScopedSetting`;
  - `CashDenomination`;
  - `CashPaymentMethod`;
  - `CashOperationLimit`;
  - `CashAlertRule`.
- La ruta legacy de UI `execute(section, name, value, ...)` queda como adaptador
  de compatibilidad hacia comandos tipados, sin escritura dual ni repositorio
  paralelo.
- Se preserva atomicidad:
  - catálogo;
  - auditoría;
  - evento;
  - outbox;
  en la misma `CashRegisterUnitOfWork`.

## Archivos modificados

- `backend/application/cash_register/configuration_use_cases.py`
- `tests/integration/cash_register/test_cash_register_configuration_schema.py`

## Evidencia de pruebas

```text
python -m unittest tests.integration.cash_register.test_cash_register_configuration_schema tests.unit.cash_register.test_cash_register_configuration -v
Ran 11 tests in 0.258s
OK

python -m unittest discover tests\unit\cash_register
Ran 92 tests in 0.213s
OK

python -m unittest discover tests\integration\cash_register
Ran 96 tests in 3.557s
OK

python -m unittest discover tests\architecture -p "test_cash*.py"
Ran 92 tests in 2.420s
OK

python -m unittest discover tests\e2e -p "*cash*.py"
Ran 11 tests in 0.683s
OK
```

## Riesgos cubiertos

- Configuración monetaria aceptada como texto libre sin validación de dominio.
- Límites con `hard_cap < approval_threshold`.
- Alertas sin canales tipados.
- Alcances no UUIDv7 para configuraciones específicas.
- Regresión de la UI actual que aún envía payload genérico.

## Veredicto

NO LISTO PARA MERGE global.

FASE 12 queda cerrada, pero el bounded context completo de Caja todavía depende
de las fases posteriores y de la validación final.
