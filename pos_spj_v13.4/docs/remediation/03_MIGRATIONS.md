# Fase 3: migraciones obligatorias y bloqueo del arranque

Fecha de validación: 2026-09-05. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
HEAD de partida: `51112b59c7737480e76baedc7a83fa06c497126b`; cambios locales sin publicar.

## Problema y resultado

El motor omitía importaciones fallidas y continuaba después de excepciones de ejecución o commit. El arranque podía tratar como utilizable una base parcialmente migrada. Ahora detiene la secuencia con `MigrationImportError`, `MigrationContractError` o `MigrationExecutionError`, conserva la causa original e intenta rollback. También propaga fallos al crear, consultar o escribir el registro de migraciones. Un fallo de rollback queda adjunto al error; no permite continuar.

`DatabaseMigrationStep` convierte el fallo en `BootstrapSeverity.FATAL`, incluida la importación del motor. La prueba de `main.py` verifica que no se construyan servicios ni la ventana después del fallo. Se eliminó la reparación automática que borraba el registro de m000 para volver a ejecutarla.

El helper de bloques obligatorios de m000 ahora propaga los errores. Al ejecutar el registro completo sobre SQLite en memoria aparecieron tres migraciones obsoletas que el motor anterior ocultaba. Se corrigió la fuente:

- 024: retiradas la segunda definición de `caja_operations`, sus índices incompatibles y la creación de `movimientos_caja`.
- 029: retirado el parche de `movimientos_caja`; se conservan los cambios de devoluciones y notas de crédito.
- 080: eliminado el módulo y su registro; solo modificaba `cierres_caja` y `movimientos_caja`, sustituidas por el esquema canónico de Caja.

Las 232 entradas restantes terminan en una base nueva. No se crea una migración de rescate ni se modifica una base operativa para obtener este resultado. La prueba comprueba el registro completo, ausencia de usuarios predeterminados, ausencia de las dos tablas retiradas y `PRAGMA foreign_key_check` vacío.

## Pruebas y evidencia

Comandos desde el paquete real `pos_spj_v13.4/`, con `../.venv/Scripts/python.exe`:

```text
python -m pytest tests/unit/bootstrap/test_migrations_fail_fast.py -q -p no:cacheprovider --tb=short
```

Resultado: **8 passed**. Antes de corregir el motor se observaron seis fallos; las dos protecciones adicionales del bloque base y del registro completo también fallaron antes de retirar las operaciones obsoletas. Se cubren importación, contrato ausente/no ejecutable, interrupción de la secuencia, registro no aplicado tras error, rollback del commit fallido y bloqueo del paso UI.

```text
python -m pytest tests/unit/bootstrap tests/integration/bootstrap tests/integration/cash_register/test_cash_register_schema_born_clean.py tests/integration/cash_register/test_cash_register_configuration_schema.py tests/integration/cash_register/test_cash_register_unit_of_work.py -q -p no:cacheprovider --tb=short
```

Resultado: **259 passed**, ejecución con elevación por ACL de los directorios temporales de pytest. La ejecución previa en sandbox encontró errores de acceso; no se modificaron las pruebas para evitarlos. Este conjunto incluye la cancelación del aprovisionamiento y el fallo real del motor desde `main.py`.

## Riesgos residuales

El motor detiene los fallos que recibe. Varias migraciones históricas aún hacen commits internos y algunas capturan excepciones propias: no se certifica atomicidad de una migración completa ni ausencia global de errores ocultos. Los bloques ya confirmados antes de un fallo pueden permanecer en disco, pero el fallo impide abrir la UI. El registro y esos módulos deben seguir depurándose durante la eliminación de legacy.

El esquema completo todavía incluye tablas legacy y dinero `REAL`; los resultados anteriores no certifican integridad Enterprise global. No se ejecutó una validación visual manual del asistente ni el conjunto completo de pruebas del repositorio en esta fase. `main.py` todavía construye `AppContainer` y `MainWindow` después de superar los gates; su sustitución continúa pendiente.

## Siguiente fase

Cerrar UUIDv7 y dinero canónico con pruebas de consumidores reales, seguido del corte de CompositionRoot, shell y Ventas. La remediación global permanece abierta.
