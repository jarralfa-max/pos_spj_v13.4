# Diseño de migración atómica UUIDv7

## Estado

```text
IN_PROGRESS
```

## Lote

```text
UUID-03-MIGRATION_DESIGN
```

## Entradas obligatorias

* `UUIDV7_SCHEMA_GRAPH.json`.
* `UUIDV7_SCHEMA_CLASSIFICATION.json`.
* `work_queue.json`.
* DB real de prueba antes de ejecutar cualquier migración destructiva.

## Decisiones de diseño no negociables

* La migración será de corte total, global y atómico.
* No habrá runtime con identidad dual.
* Los mapas `old_id -> uuid` solo existirán dentro de la transacción de migración.
* Toda tabla funcional clasificada debe terminar con PK/FK UUID.
* Todo fallo ejecuta rollback y obliga a restaurar backup verificado.

## Algoritmo inicial

```text
1. Cerrar aplicación.
2. Verificar backup SQLite.
3. Bloquear instancia.
4. Abrir transacción exclusiva.
5. Crear tablas nuevas UUID.
6. Crear mapas temporales old_id -> uuid solo en memoria/transacción.
7. Copiar datos y reescribir PK/FK.
8. Validar conteos.
9. Ejecutar PRAGMA foreign_key_check.
10. Ejecutar PRAGMA integrity_check.
11. Eliminar tablas antiguas.
12. Renombrar tablas nuevas.
13. Commit.
14. Eliminar mapas temporales.
```

## Siguiente trabajo

Completar diseño tabla por tabla a partir de `UUIDV7_SCHEMA_CLASSIFICATION.json` y crear `migrations/standalone/200_uuid_only_schema_cutover.py` con tests de protección antes de ejecutar sobre datos reales.
