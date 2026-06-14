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
|     0 | UUIDV7_CUTOVER        | Corte global UUIDv7      | PENDING |
|     1 | CONFIGURACION         | Configuración            | PENDING |
|     2 | MERMA                 | Merma                    | PENDING |
|     3 | PRODUCTOS             | Productos                | PENDING |
|     4 | INVENTARIO            | Inventario               | PENDING |
|     5 | VENTAS                | Ventas                   | PENDING |
|     6 | PROCESAMIENTO_CARNICO | Procesamiento cárnico    | PENDING |
|     7 | RECETAS               | Recetas                  | PENDING |
|     8 | PRODUCCION            | Producción               | PENDING |
|     9 | TRANSFERENCIAS        | Transferencias           | PENDING |
|    10 | COMPRAS               | Compras                  | PENDING |
|    11 | RECEPCION             | Recepción                | PENDING |
|    12 | PLANEACION_COMPRAS    | Planeación de compras    | PENDING |
|    13 | COTIZACIONES          | Cotizaciones             | PENDING |
|    14 | PEDIDOS               | Pedidos                  | PENDING |
|    15 | DELIVERY              | Delivery                 | PENDING |
|    16 | WHATSAPP              | WhatsApp                 | PENDING |
|    17 | CLIENTES              | Clientes                 | PENDING |
|    18 | PROVEEDORES           | Proveedores              | PENDING |
|    19 | CAJA                  | Caja                     | PENDING |
|    20 | FINANZAS              | Finanzas                 | PENDING |
|    21 | CUENTAS_COBRAR        | Cuentas por cobrar       | PENDING |
|    22 | CUENTAS_PAGAR         | Cuentas por pagar        | PENDING |
|    23 | ACTIVOS               | Activos                  | PENDING |
|    24 | MANTENIMIENTO         | Mantenimiento            | PENDING |
|    25 | RRHH                  | Recursos humanos         | PENDING |
|    26 | FIDELIDAD             | Fidelidad                | PENDING |
|    27 | TARJETAS_FIDELIDAD    | Tarjetas de fidelidad    | PENDING |
|    28 | PROMOCIONES           | Promociones              | PENDING |
|    29 | TICKETS               | Tickets                  | PENDING |
|    30 | ETIQUETAS             | Etiquetas                | PENDING |
|    31 | HARDWARE              | Hardware                 | PENDING |
|    32 | NOTIFICACIONES        | Notificaciones           | PENDING |
|    33 | DASHBOARD             | Dashboard                | PENDING |
|    34 | BI                    | Inteligencia de negocios | PENDING |
|    35 | REPORTES              | Reportes                 | PENDING |
|    36 | API                   | API FastAPI              | PENDING |
|    37 | SINCRONIZACION        | Sincronización           | PENDING |
|    38 | INSTALADOR            | Instalador               | PENDING |
|    39 | ACTUALIZADOR          | Actualizador             | PENDING |
|    40 | CIERRE_GLOBAL         | Cierre global            | PENDING |

## Regla

Codex selecciona siempre el primer módulo que no esté en `DONE`, salvo que una dependencia documentada obligue a reordenar temporalmente la cola.
