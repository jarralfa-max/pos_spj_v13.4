# Módulo actual

## Código

```text
UUIDV7_CUTOVER
```

## Nombre

Corte global de identidad UUIDv7.

## Estado

```text
PENDING
```

## Iteración

```text
0
```

## Objetivo

Eliminar por completo:

* IDs enteros funcionales;
* PK y FK enteras;
* `AUTOINCREMENT`;
* `lastrowid`;
* casts `int(..._id)`;
* `legacy_id`;
* escritura dual;
* lectura dual;
* fallback de identidad;
* tablas paralelas.

## Hallazgos abiertos

Pendientes de auditoría inicial.

## Tests requeridos

Pendientes de auditoría inicial.

## Bloqueos

Ninguno registrado.

## Próxima acción

Ejecutar auditoría completa del esquema y contratos de identidad.
