# WhatsApp Event Catalog — pos_spj v13.4

Catálogo de eventos emitidos y consumidos por el microservicio WhatsApp.

---

## Eventos EMITIDOS por el microservicio WA → ERP EventBus

| Constante | Tipo de evento | Payload clave | Prioridad |
|-----------|---------------|---------------|-----------|
| `WA_PEDIDO_CREADO` | `WA_PEDIDO_CREADO` | `folio`, `cliente_id`, `items`, `total` | 80 |
| `WA_COTIZACION_CREADA` | `WA_COTIZACION_CREADA` | `cotizacion_id`, `total`, `cliente_id` | 50 |
| `WA_VENTA_CONFIRMADA` | `WA_VENTA_CONFIRMADA` | `venta_id`, `folio`, `total`, `cliente_id` | 80 |
| `WA_ANTICIPO_REQUERIDO` | `WA_ANTICIPO_REQUERIDO` | `venta_id`, `monto`, `tipo` | 80 |
| `WA_ANTICIPO_PAGADO` | `WA_ANTICIPO_PAGADO` | `venta_id`, `monto`, `metodo`, `referencia` | 80 |
| `WA_ALERTA_GENERADA` | `WA_ALERTA_GENERADA` | `tipo`, `mensaje`, `sucursal_id` | 30 |
| `WA_CLIENTE_REGISTRADO` | `WA_CLIENTE_REGISTRADO` | `cliente_id`, `phone`, `nombre` | 50 |
| `QUOTE_CREATED` | `QUOTE_CREATED` | `cotizacion_id`, `total`, `cliente_id` | 50 |
| `SALE_CREATED` | `SALE_CREATED` | `venta_id`, `folio`, `total`, `cliente_id` | 80 |
| `PAYMENT_REQUIRED` | `PAYMENT_REQUIRED` | `venta_id`, `monto`, `tipo` | 80 |
| `PAYMENT_RECEIVED` | `PAYMENT_RECEIVED` | `venta_id`, `monto`, `metodo`, `referencia` | 80 |
| `PURCHASE_ORDER_CREATED` | `PURCHASE_ORDER_CREATED` | `oc_id`, `producto_id`, `cantidad` | 50 |
| `DELIVERY_SCHEDULED` | `DELIVERY_SCHEDULED` | `venta_id`, `fecha`, `tipo_entrega` | 50 |
| `DELIVERY_CONFIRMED` | `DELIVERY_CONFIRMED` | `venta_id`, `folio` | 80 |
| `PAYMENT_REMINDER` | `PAYMENT_REMINDER` | `venta_id`, `folio`, `monto`, `phone` | 10 |
| `CLIENT_CONFIRMATION_REQUIRED` | `CLIENT_CONFIRMATION_REQUIRED` | `venta_id`, `folio`, `phone` | 80 |
| `DELIVERY_REMINDER` | `DELIVERY_REMINDER` | `venta_id`, `folio`, `fecha`, `phone` | 10 |
| `PURCHASE_FOLLOWUP_REMINDER` | `PURCHASE_FOLLOWUP_REMINDER` | `oc_id`, `producto`, `phone` | 10 |
| `STAFF_NOTIFICATION` | `STAFF_NOTIFICATION` | `mensaje`, `tipo`, `sucursal_id` | 30 |
| `VACATION_REMINDER` | `VACATION_REMINDER` | `empleado_id`, `nombre`, `fecha_inicio` | 10 |
| `FORECAST_DEMAND_UPDATED` | `FORECAST_DEMAND_UPDATED` | `producto_id`, `demanda_est`, `periodo` | 5 |

### Metadata estándar (siempre incluida)

Todos los eventos emitidos por `WAEventEmitter.emit()` incluyen:

```json
{
  "sucursal_id": 1,
  "prioridad": 5,
  "timestamp": "2026-05-20T10:00:00.000",
  "canal": "whatsapp"
}
```

---

## Eventos CONSUMIDOS por el microservicio WA ← ERP EventBus

| Constante | Tipo de evento | Acción en WA | Descripción |
|-----------|---------------|-------------|-------------|
| `ERP_STOCK_BAJO` | `STOCK_BAJO_MINIMO` | Notificar staff vía WA | Stock de producto por debajo del mínimo |
| `ERP_VENTA_COMPLETADA` | `VENTA_COMPLETADA` | Confirmar al cliente | Venta cerrada en el ERP |
| `ERP_AJUSTE_INVENTARIO` | `AJUSTE_INVENTARIO` | Log / alerta | Ajuste manual de inventario |
| `ERP_PAYROLL_DUE` | `PAYROLL_DUE` | Notificar RRHH | Nómina pendiente de pago |
| `ERP_EMPLOYEE_REST_DAY` | `EMPLOYEE_REST_DAY` | Notificar empleado | Día de descanso asignado |
| `ERP_EMPLOYEE_OVERWORK` | `EMPLOYEE_OVERWORK` | Alerta RRHH | Empleado con exceso de horas |
| `ERP_FORECAST_GENERADO` | `FORECAST_GENERADO` | Reporte a gerencia | Nuevo forecast de demanda generado |

---

## Persistencia de eventos

Todos los eventos emitidos se registran en la tabla `wa_event_log` de la base de datos del ERP:

```sql
CREATE TABLE IF NOT EXISTS wa_event_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    data_json  TEXT,                           -- JSON serializado (max 4000 chars)
    sucursal_id INTEGER DEFAULT 1,
    prioridad   INTEGER DEFAULT 5,
    timestamp   TEXT DEFAULT (datetime('now'))
);
```

---

## Prioridades del EventBus

| Prioridad | Uso |
|-----------|-----|
| 100 | Sync inmediato (inventario, ventas) |
| 80 | Operaciones críticas de negocio |
| 50 | Contabilidad / ledger |
| 30 | Auditoría |
| 10 | Notificaciones secundarias |
| 5 | Analytics / BI |

Los eventos con `prioridad <= 2` se publican de forma síncrona al bus; el resto se publican de forma asíncrona para no bloquear el flujo de WhatsApp.

---

## Archivos relacionados

- `whatsapp_service/erp/events.py` — `WAEventEmitter`, definición de constantes
- `pos_spj_v13.4/core/events/event_bus.py` — EventBus del ERP
- `pos_spj_v13.4/core/integrations/whatsapp_client.py` — Cliente REST WA desde el ERP
