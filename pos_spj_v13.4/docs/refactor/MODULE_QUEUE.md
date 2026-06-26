# Cola maestra de mÃ³dulos

## Estados permitidos

```text
PENDING
AUDIT
PROTECTION
IMPLEMENTATION
LEGACY_REMOVAL
INTEGRATION
VALIDATION
BLOCKED
DONE
```

## Cola

| Orden | CÃ³digo                | MÃ³dulo                   | Estado  |
| ----: | --------------------- | ------------------------ | ------- |
<<<<<<< HEAD
|     1 | CONFIGURACION         | Configuración            | AUDIT   |
|     2 | MERMA                 | Merma                    | DONE |
|     3 | PRODUCTOS             | Productos                | DONE |
|     4 | INVENTARIO            | Inventario               | PENDING |
|     5 | VENTAS                | Ventas                   | PENDING |
|     6 | PROCESAMIENTO_CARNICO | Procesamiento cárnico    | DONE |
|     7 | RECETAS               | Recetas                  | PENDING |
|     8 | PRODUCCION            | Producción               | PENDING |
|     9 | TRANSFERENCIAS        | Transferencias           | DONE |
|    10 | DELIVERY              | Delivery                 | DONE |
|    11 | CAJA                  | Caja                     | DONE |
=======
|     1 | CONFIGURACION         | ConfiguraciÃ³n            | IMPLEMENTATION |
|     2 | MERMA                 | Merma                    | PENDING |
|     3 | PRODUCTOS             | Productos                | PENDING |
|     4 | INVENTARIO            | Inventario               | PENDING |
|     5 | VENTAS                | Ventas                   | PENDING |
|     6 | PROCESAMIENTO_CARNICO | Procesamiento cÃ¡rnico    | PENDING |
|     7 | RECETAS               | Recetas                  | PENDING |
|     8 | PRODUCCION            | ProducciÃ³n               | PENDING |
|     9 | TRANSFERENCIAS        | Transferencias           | PENDING |
|    10 | DELIVERY              | Delivery                 | PENDING |
|    11 | CAJA                  | Caja                     | PENDING |
>>>>>>> claude/intelligent-clarke-uq1ck7
|    12 | BI_DASHBOARD          | BI / Dashboard           | PENDING |
|    13 | PLANEACION_COMPRAS    | PlaneaciÃ³n de compras    | PENDING |
|    14 | COTIZACIONES          | Cotizaciones             | PENDING |
|    15 | FIDELIDAD             | Fidelidad                | PENDING |
|    16 | TARJETAS_FIDELIDAD    | Tarjetas de fidelidad    | PENDING |
|    17 | ACTIVOS               | Activos                  | PENDING |
|    18 | CLIENTES              | Clientes                 | PENDING |
|    19 | PROVEEDORES           | Proveedores              | PENDING |
|    20 | COMPRAS               | Compras                  | PENDING |
|    21 | RECEPCION             | RecepciÃ³n                | PENDING |
|    22 | PEDIDOS               | Pedidos                  | PENDING |
|    23 | TICKETS               | Tickets                  | PENDING |
|    24 | ETIQUETAS             | Etiquetas                | PENDING |
|    25 | HARDWARE              | Hardware                 | PENDING |
|    26 | NOTIFICACIONES        | Notificaciones           | PENDING |
|    27 | WHATSAPP              | WhatsApp                 | PENDING |
|    28 | FINANZAS              | Finanzas                 | PENDING |
|    29 | RRHH                  | Recursos humanos         | PENDING |
|    30 | REPORTES              | Reportes                 | PENDING |
|    31 | API                   | API FastAPI              | PENDING |
|    32 | SINCRONIZACION        | SincronizaciÃ³n           | PENDING |
|    33 | INSTALADOR            | Instalador               | PENDING |
|    34 | ACTUALIZADOR          | Actualizador             | PENDING |
|    35 | CIERRE_GLOBAL         | Cierre global            | PENDING |

## Regla

Codex selecciona siempre el primer mÃ³dulo que no estÃ© en `DONE`, salvo que una dependencia documentada obligue a reordenar temporalmente la cola.

## Fuente de autoridad

La cola sigue `SPJ_REFACTOR_SKILL.md`; UUIDv7 se trata como lote obligatorio dentro de cada mÃ³dulo, no como sustituto del refactor completo.
