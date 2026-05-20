# WHATSAPP_ARCHITECTURE.md — Arquitectura WhatsApp SPJ POS v13.4

Generado: 2026-05-20

---

## Visión general

```
                    Meta Cloud API
                         │
                    POST /webhook
                         │
                 ┌───────▼────────┐
                 │  whatsapp_     │
                 │  service/      │  FastAPI microservicio
                 │  (puerto 8000) │
                 └───────┬────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
   ┌──────▼─────┐ ┌──────▼──────┐ ┌────▼──────────┐
   │  parser/   │ │   flows/    │ │ router/       │
   │ intent_    │ │ pedido,cot, │ │ notify_router │◄── ERP POS
   │ parser.py  │ │ pago, etc.  │ │ (auth: API key│
   └──────┬─────┘ └──────┬──────┘ └───────────────┘
          │              │
          └──────┬────────┘
                 │
          ┌──────▼────────┐
          │  erp/bridge   │  Gateways: Customer, Order,
          │  .py          │  Quote, Payment, Inventory,
          └──────┬────────┘  Delivery
                 │
     ┌───────────┼───────────┐
     │           │           │
┌────▼───┐  ┌────▼────┐  ┌───▼─────┐
│ REST   │  │ SQLite  │  │EventBus │
│ API    │  │ fallback│  │ERP      │
│(prod)  │  │(dev)    │  │         │
└────────┘  └─────────┘  └─────────┘
```

---

## Componentes ERP POS

```
pos_spj_v13.4/
├── modulos/whatsapp_module.py          ← UI SOLO (PyQt5)
│       └── usa WhatsAppAdminService
│
├── core/
│   ├── services/
│   │   ├── whatsapp_admin_service.py   ← Facade admin (NUEVO)
│   │   ├── whatsapp_credential_service.py ← Credenciales seguras (NUEVO)
│   │   └── whatsapp_service.py         ← Legacy: cola offline + Meta/Twilio
│   ├── repositories/
│   │   ├── whatsapp_config_repository.py  ← CRUD config (NUEVO)
│   │   ├── whatsapp_history_repository.py ← Historial unificado (NUEVO)
│   │   └── whatsapp_metrics_repository.py ← Métricas (NUEVO)
│   └── integrations/
│       └── whatsapp_client.py          ← REST client → microservicio
│
├── services/whatsapp_service.py        ← SHIM v12 (mantener)
└── integrations/whatsapp_service.py   ← SHIM v12 (mantener)
```

---

## Flujo: Mensaje entrante

```
Meta → POST /webhook
  → webhook/whatsapp.py (idempotencia + rate limit)
  → IncomingMessage.from_webhook()
  → NumberRouter.route() → NumeroConfig (sucursal)
  → MessageRouter.route()
  → IntentParser (regex → fuzzy → Ollama)
  → Flow (pedido / cotizacion / pago / registro / menu)
  → ERPBridge (read-only consultas / write via API)
  → WAEventEmitter.emit()
  → messaging/sender.py → Meta Graph API
```

---

## Flujo: Notificación ERP → Cliente

```
ERP POS (cualquier módulo)
  → WhatsAppClient.notificar_pedido_listo(phone, folio)
  → POST /api/notify/pedido-listo  [X-Internal-Key: ...]
  → notify_router.pedido_listo()
  → messaging/sender.send_text()
  → Meta Graph API
```

---

## Credenciales y seguridad

| Credencial | Almacenamiento | Acceso |
|-----------|----------------|--------|
| `meta_token` | `whatsapp_numeros.meta_token` (SQLite) | Solo `WhatsAppCredentialService` |
| `WA_ACCESS_TOKEN` | `.env` microservicio | Solo `sender.py` |
| `WA_INTERNAL_API_KEY` | `.env` microservicio | `notify_router` + `WhatsAppClient` |
| `WA_VERIFY_TOKEN` | `.env` / `configuraciones` | `webhook/whatsapp.py` |
| `MP_ACCESS_TOKEN` | `.env` microservicio | `webhook/mercadopago.py` |

**Reglas:**
- Tokens nunca se loguean completos (usar `_mask_token()`)
- `X-Internal-Key` protege endpoints notify en producción
- En modo dev sin `WA_INTERNAL_API_KEY`: warning en log, no bloquea

---

## Tablas críticas

| Tabla | Tipo | Nota |
|-------|------|------|
| `whatsapp_numeros` | Config | Fuente canónica de credenciales por sucursal |
| `wa_event_log` | Audit | Todo evento WA queda registrado |
| `wa_message_queue` | Queue | Cola de salida (legacy WhatsAppService) |
| `configuraciones` | KV store | Prefijo `wa_` para config del bot |

---

## Checklist producción

- [ ] Meta: configurar Webhook URL pública en Business Manager
- [ ] `WA_PHONE_NUMBER_ID` y `WA_ACCESS_TOKEN` en `.env` del microservicio
- [ ] `WA_INTERNAL_API_KEY` generado (≥32 chars hex)
- [ ] Número registrado en `whatsapp_numeros` con `activo=1`
- [ ] `ERP_DB_PATH` correcto en `.env`
- [ ] `ERP_API_URL` + `ERP_API_KEY` para writes por use cases
- [ ] Microservicio health OK
- [ ] Webhook Meta verificado (GET /webhook retorna challenge)
- [ ] Test E2E: enviar mensaje a WA → recibir respuesta del bot
