# WHATSAPP_EVENT_CATALOG.md — Catálogo de eventos WA

Generado: 2026-05-20 | SPJ POS v13.4

Prioridades según CLAUDE.md: 100=sync inmediato, 80=crítico negocio, 50=contabilidad, 30=auditoría, 10=notificaciones, 5=analytics.

---

## Eventos EMITIDOS por WhatsApp → ERP

| Evento | Prioridad | Crítico | Productor | Consumidor esperado | Cuándo se emite |
|--------|-----------|---------|-----------|---------------------|-----------------|
| `WA_PEDIDO_CREADO` | 80 | ✅ Síncrono | `pedido_flow.py` | `ventas`, `inventario`, `delivery` | Al confirmar pedido desde WA |
| `WA_COTIZACION_CREADA` | 50 | ❌ Async | `cotizacion_flow.py` | `cotizaciones` | Al crear cotización desde WA |
| `WA_VENTA_CONFIRMADA` | 80 | ✅ Síncrono | `pago_flow.py` | `finanzas`, `delivery` | Al confirmar pago |
| `WA_ANTICIPO_REQUERIDO` | 80 | ✅ Síncrono | `pedido_flow.py` | `finanzas` | Al detectar que se requiere anticipo |
| `WA_ANTICIPO_PAGADO` | 80 | ✅ Síncrono | `webhook/mercadopago.py` | `finanzas`, `delivery` | Al recibir confirmación MercadoPago |
| `WA_CLIENTE_REGISTRADO` | 30 | ❌ Async | `registro_flow.py` | `crm`, `loyalty` | Al crear cliente mínimo desde WA |
| `WA_ALERTA_GENERADA` | 10 | ❌ Async | `notifications/alerts.py` | `dashboard` | Alertas de operación |

### Payloads

#### `WA_PEDIDO_CREADO`
```json
{
  "venta_id": 123,
  "folio": "WA-ABC12345",
  "total": 450.00,
  "cliente_id": 45,
  "items": [{"producto_id": 1, "nombre": "Tacos", "cantidad": 2.0, "precio_unitario": 225.0}],
  "tipo_entrega": "domicilio",
  "sucursal_id": 1,
  "canal": "whatsapp",
  "prioridad": 80,
  "timestamp": "2026-05-20T12:00:00"
}
```

#### `WA_COTIZACION_CREADA`
```json
{
  "cotizacion_id": 10,
  "folio": "CWA-XY1234",
  "total": 300.00,
  "cliente_id": 45,
  "sucursal_id": 1,
  "canal": "whatsapp",
  "prioridad": 50,
  "timestamp": "2026-05-20T12:01:00"
}
```

#### `WA_ANTICIPO_PAGADO`
```json
{
  "venta_id": 123,
  "monto": 225.00,
  "metodo": "mercadopago",
  "referencia": "MP-REF-001",
  "sucursal_id": 1,
  "canal": "whatsapp",
  "prioridad": 80,
  "timestamp": "2026-05-20T12:05:00"
}
```

---

## Eventos ESCUCHADOS del ERP → WhatsApp reacciona

| Evento ERP | Prioridad | Qué hace WA |
|-----------|-----------|-------------|
| `STOCK_BAJO_MINIMO` | 100 | Notifica a staff de compras por WA |
| `VENTA_COMPLETADA` | 80 | No emite (evitar duplicar) — ver nota idempotencia |
| `PAYROLL_DUE` | 80 | Notifica a empleados por WA (RRHH) |
| `EMPLOYEE_REST_DAY` | 50 | Notifica confirmación descanso |
| `EMPLOYEE_OVERWORK` | 80 | Alerta de sobrecarga a supervisor |
| `FORECAST_GENERADO` | 5 | Notificación analítica a gerencia |

---

## Nota: Idempotencia

Todos los eventos incluyen `timestamp` + `canal: "whatsapp"`.
El consumidor debe verificar que no haya procesado ya el mismo `venta_id` / `cotizacion_id`.

`WA_PEDIDO_CREADO` y `VENTA_COMPLETADA` (ERP) pueden referirse al mismo pedido.
El ERP no debe emitir `VENTA_COMPLETADA` para ventas `canal='whatsapp'` si WA ya emitió `WA_VENTA_CONFIRMADA`.

---

## Nota: Retry

Los eventos críticos (prioridad ≥ 80) son síncronos en `WAEventEmitter.emit()`.
Si el EventBus no está disponible, se loguea en `wa_event_log` para reprocesamiento manual.
Cola de mensajes con retry automático: **pendiente Fase 6**.
