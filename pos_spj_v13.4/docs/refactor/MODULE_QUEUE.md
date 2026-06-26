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
|     3 | INVENTARIO            | Inventario               | PENDING |
|     4 | VENTAS                | Ventas                   | DONE |
|     5 | PROCESAMIENTO_CARNICO | Procesamiento cárnico    | DONE |
|     6 | RECETAS               | Recetas                  | PENDING |
|     7 | PRODUCCION            | Producción               | PENDING |
|     8 | TRANSFERENCIAS        | Transferencias           | DONE |
|     9 | DELIVERY              | Delivery                 | DONE |
|    10 | CAJA                  | Caja                     | DONE |
|    11 | BI_DASHBOARD          | BI / Dashboard           | PENDING |
|    12 | PLANEACION_COMPRAS    | Planeación de compras    | PENDING |
|    13 | COTIZACIONES          | Cotizaciones             | PENDING |
|    14 | FIDELIDAD             | Fidelidad                | PENDING |
|    15 | TARJETAS_FIDELIDAD    | Tarjetas de fidelidad    | PENDING |
|    16 | ACTIVOS               | Activos                  | PENDING |
|    17 | CLIENTES              | Clientes                 | PENDING |
|    18 | PROVEEDORES           | Proveedores              | PENDING |
|    19 | COMPRAS               | Compras                  | PENDING |
|    20 | RECEPCION             | Recepción                | PENDING |
|    21 | PEDIDOS               | Pedidos                  | PENDING |
|    22 | TICKETS               | Tickets                  | PENDING |
|    23 | ETIQUETAS             | Etiquetas                | PENDING |
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
