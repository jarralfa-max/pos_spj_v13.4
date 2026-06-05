# WhatsApp Admin Console — UI Layout

**Archivo principal:** `modulos/whatsapp/whatsapp_module.py`  
**Shim de compatibilidad:** `modulos/whatsapp_module.py`  
**Versión:** SPJ ERP v13.4

---

## Estructura de carpetas

```
modulos/whatsapp/
├── __init__.py                    # Re-exporta ModuloWhatsApp
├── whatsapp_module.py             # Módulo principal (QTabWidget con 7 tabs)
├── panels/
│   ├── __init__.py
│   ├── status_panel.py            # Tab 1: Estado general
│   ├── credentials_panel.py       # Tab 2: Meta / Credenciales
│   ├── numbers_panel.py           # Tab 3: Números y canales
│   ├── policies_panel.py          # Tab 4: Políticas
│   ├── webhook_panel.py           # Tab 5: Webhook / Microservicio
│   ├── history_panel.py           # Tab 6: Historial
│   └── diagnostics_panel.py       # Tab 7: Diagnóstico
└── widgets/
    ├── __init__.py
    ├── status_card.py             # StatusCard, MetricCard
    ├── masked_secret_field.py     # MaskedSecretField
    ├── connection_badge.py        # StatusBadge, ConnectionBadge
    ├── policy_table.py            # PolicyTable
    ├── empty_state.py             # EmptyState
    └── error_panel.py             # ErrorPanel
```

---

## Tabs y responsabilidades

| # | Tab | Panel | Propósito |
|---|-----|-------|-----------|
| 1 | Estado | `StatusPanel` | Conexión WA, 6 métricas, estado del bot |
| 2 | Meta / Credenciales | `CredentialsPanel` | Phone Number ID, tokens, URL microservicio |
| 3 | Números y canales | `NumbersPanel` | CRUD de líneas WA por sucursal |
| 4 | Políticas | `PoliciesPanel` | Tabla de política WA_STAFF (solo lectura) |
| 5 | Webhook | `WebhookPanel` | Control servidor webhook Meta → ERP |
| 6 | Historial | `HistoryPanel` | Búsqueda/auditoría de mensajes |
| 7 | Diagnóstico | `DiagnosticsPanel` | Test conectividad + log |

---

## Widgets reutilizables

| Widget | Descripción |
|--------|-------------|
| `StatusCard` | Tarjeta con título + valor + indicador de estado |
| `MetricCard` | Tarjeta con número grande coloreado + subtítulo |
| `MaskedSecretField` | Campo de token con patrón "Reemplazar" — nunca muestra valor completo |
| `StatusBadge` | Pill coloreado (ok / warning / error / neutral / loading) |
| `ConnectionBadge` | Punto de color + etiqueta de texto para estado de conexión |
| `PolicyTable` | Tabla de política WA_STAFF_ALLOWED / WA_STAFF_FORBIDDEN (solo lectura) |
| `EmptyState` | Placeholder para listas vacías con ícono + acción opcional |
| `ErrorPanel` | Banner de error con opción de reintento |

---

## Reglas de diseño

- **Tokens de diseño:** todos los colores, espaciados y radios provienen de `modulos/design_tokens.py`
- **Botones:** todos vía `spj_btn(btn, variant)` — sin estilos inline en botones
- **Sin SQL:** ningún widget ejecuta SQL directo; todo delega a `WhatsAppAdminService` o `WhatsAppCredentialService`
- **Sin tokens visibles:** `MaskedSecretField` aplica el patrón "Reemplazar" en todos los campos sensibles
- **Sin lógica de negocio:** el módulo es solo presentación y configuración

---

## Política de canales (referencia)

La política está definida en `core/services/notifications/notification_policy_service.py`.

| Tipo | Canal WA staff | ERP Inbox |
|------|---------------|-----------|
| `nomina_pagada`, `vacaciones_recordatorio`, `descanso_recordatorio` | ✅ WA | ✅ |
| `diferencia_caja`, `backup_fallido`, `alerta_seguridad`, `alerta_operacion_critica` | ✅ WA | ✅ |
| `pedido_asignado_repartidor`, `forecast_sugerencia_compra` | ✅ WA | ✅ |
| `pedido_whatsapp_nuevo`, `anticipo_*`, `venta_cancelada`, `pedido_listo` | ❌ Solo inbox | ✅ |
| `stock_bajo`, `corte_z`, `caducidad_proxima`, `cambio_estado_pedido` | ❌ Solo inbox | ✅ |

---

## Refresco automático

El módulo tiene un `QTimer` de 30 segundos que llama a `_soft_refresh()`, el cual actualiza:
- `StatusPanel.refresh()` — métricas
- `HistoryPanel.refresh()` — últimos mensajes

No realiza llamadas de red bloqueantes; solo consulta `WhatsAppAdminService.get_metrics()` y `get_history()`.
