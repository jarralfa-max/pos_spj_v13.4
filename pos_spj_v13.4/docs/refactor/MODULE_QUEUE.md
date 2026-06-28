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
|     0 | CONFIGURACION         | Configuración            | PENDING |
|     1 | MERMA                 | Merma                    | DONE |
|     2 | PRODUCTOS             | Productos                | DONE |
|     3 | INVENTARIO            | Inventario               | DONE |
|     4 | VENTAS                | Ventas                   | DONE |
|     5 | PROCESAMIENTO_CARNICO | Procesamiento cárnico    | DONE |
|     6 | RECETAS               | Recetas                  | DONE |
|     7 | PRODUCCION            | Producción               | DONE |
|     8 | TRANSFERENCIAS        | Transferencias           | DONE |
|     9 | DELIVERY              | Delivery                 | DONE |
|    10 | CAJA                  | Caja                     | DONE |
|    11 | BI_DASHBOARD          | BI / Dashboard           | DONE |
|    12 | PLANEACION_COMPRAS    | Planeación de compras    | DONE |
|    13 | COTIZACIONES          | Cotizaciones             | DONE |
|    14 | FIDELIDAD             | Fidelidad                | DONE |
|    15 | TARJETAS_FIDELIDAD    | Tarjetas de fidelidad    | DONE |
|    16 | ACTIVOS               | Activos                  | DONE |
|    17 | CLIENTES              | Clientes                 | DONE |
|    18 | PROVEEDORES           | Proveedores              | DONE |
|    19 | COMPRAS               | Compras                  | DONE |
|    20 | RECEPCION             | Recepción                | DONE |
|    21 | PEDIDOS               | Pedidos                  | DONE |
|    22 | TICKETS               | Tickets                  | DONE |
|    23 | ETIQUETAS             | Etiquetas                | DONE |
|    24 | HARDWARE              | Hardware                 | PENDING |
|    25 | NOTIFICACIONES        | Notificaciones           | PENDING |
|    26 | WHATSAPP              | WhatsApp                 | PENDING |
|    27 | FINANZAS              | Finanzas                 | PENDING |
|    28 | RRHH                  | Recursos humanos         | PENDING |
|    29 | REPORTES              | Reportes                 | PENDING |
|    30 | API                   | API FastAPI              | PENDING |
|    31 | SINCRONIZACION        | Sincronización           | PENDING |
|    32 | INSTALADOR            | Instalador               | PENDING |
|    33 | ACTUALIZADOR          | Actualizador             | PENDING |
|    34 | CIERRE_GLOBAL         | Cierre global            | PENDING |

## Regla

Codex selecciona siempre el primer módulo que no esté en `DONE`, salvo que una dependencia documentada obligue a reordenar temporalmente la cola.
