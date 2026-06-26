# Cola maestra de módulos

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

| Orden | Código                | Módulo                   | Estado  |
| ----: | --------------------- | ------------------------ | ------- |
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
|    11 | CAJA                  | Caja                     | IMPLEMENTATION |
|    12 | BI_DASHBOARD          | BI / Dashboard           | PENDING |
|    13 | PLANEACION_COMPRAS    | Planeación de compras    | PENDING |
|    14 | COTIZACIONES          | Cotizaciones             | PENDING |
|    15 | FIDELIDAD             | Fidelidad                | PENDING |
|    16 | TARJETAS_FIDELIDAD    | Tarjetas de fidelidad    | PENDING |
|    17 | ACTIVOS               | Activos                  | PENDING |
|    18 | CLIENTES              | Clientes                 | PENDING |
|    19 | PROVEEDORES           | Proveedores              | PENDING |
|    20 | COMPRAS               | Compras                  | PENDING |
|    21 | RECEPCION             | Recepción                | PENDING |
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
|    32 | SINCRONIZACION        | Sincronización           | PENDING |
|    33 | INSTALADOR            | Instalador               | PENDING |
|    34 | ACTUALIZADOR          | Actualizador             | PENDING |
|    35 | CIERRE_GLOBAL         | Cierre global            | PENDING |

## Regla

Codex selecciona siempre el primer módulo que no esté en `DONE`, salvo que una dependencia documentada obligue a reordenar temporalmente la cola.

## Fuente de autoridad

La cola sigue `SPJ_REFACTOR_SKILL.md`; UUIDv7 se trata como lote obligatorio dentro de cada módulo, no como sustituto del refactor completo.
