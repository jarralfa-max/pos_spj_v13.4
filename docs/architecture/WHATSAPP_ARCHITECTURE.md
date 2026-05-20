# WhatsApp Microservice Architecture — pos_spj v13.4

## Overview

The WhatsApp microservice is an independent FastAPI service that acts as a bidirectional gateway between the POS/ERP core and the WhatsApp Cloud API. It handles inbound customer messages, manages conversational state, and sends proactive notifications triggered by ERP events.

```
┌─────────────────────────────────────────────────────────────────┐
│                        WhatsApp Cloud API                       │
│                   (graph.facebook.com/v21.0)                    │
└────────────────────────┬──────────────────┬─────────────────────┘
                         │ webhook (inbound) │ REST (outbound)
                         ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│               whatsapp_service/ (FastAPI :8000)                 │
│                                                                 │
│  webhook/whatsapp.py ──► router/message_router.py              │
│  webhook/mercadopago.py     │                                   │
│  router/notify_router.py ◄──┼── POS Core (X-Internal-Key)      │
│                             │                                   │
│  state/conversation.py ◄────┤ (SQLite: conversations.db)       │
│  parser/intent_parser.py ◄──┤                                   │
│  parser/product_matcher.py  │                                   │
│  parser/llm_local.py ◄──────┘ (Ollama/DeepSeek)               │
│                                                                 │
│  erp/bridge.py ────────────────────► ERP SQLite DB             │
│  erp/events.py ────────────────────► ERP EventBus              │
│  messaging/sender.py ──────────────► WA Cloud API              │
│  config/numbers.py                                              │
│  config/schedules.py                                            │
│  config/settings.py                                             │
│  middleware/handoff.py                                          │
└─────────────────────────────────────────────────────────────────┘
                         │
                         │ EventBus (publish/subscribe)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│               pos_spj_v13.4/ (ERP Core)                        │
│                                                                 │
│  core/events/event_bus.py                                       │
│  core/integrations/whatsapp_client.py ──► /api/notify/*        │
│  core/services/enterprise/                                      │
│  repositories/                                                  │
│  modulos/ (PyQt5 UI)                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
whatsapp_service/
├── main.py                    # FastAPI app entrypoint, lifespan wiring
├── .env.example               # Environment variable template
├── config/
│   ├── settings.py            # Centralized config (env vars)
│   ├── numbers.py             # NumberRegistry — phone → sucursal mapping
│   └── schedules.py           # ScheduleService — business hours
├── erp/
│   ├── bridge.py              # ERPBridge — direct SQLite read/write to ERP DB
│   └── events.py              # WAEventEmitter — publishes to ERP EventBus
├── messaging/
│   └── sender.py              # send_text() — calls WA Cloud API
├── middleware/
│   └── handoff.py             # HandoffService — escalation to human agent
├── parser/
│   ├── intent_parser.py       # IntentParser — NLP pipeline (3 levels)
│   ├── product_matcher.py     # ProductMatcher — fuzzy product search
│   └── llm_local.py           # OllamaClient — local LLM fallback (DeepSeek)
├── router/
│   ├── message_router.py      # MessageRouter — conversation flow orchestrator
│   ├── notify_router.py       # REST /api/notify/* — proactive notifications
│   └── number_router.py       # NumberRouter — multi-sucursal routing
├── state/
│   └── conversation.py        # ConversationStore — SQLite conversation state
└── webhook/
    ├── whatsapp.py            # POST /webhook — inbound WA messages
    └── mercadopago.py         # POST /webhook/mp — MercadoPago callbacks
```

---

## Request Flows

### 1. Inbound Customer Message (WA → ERP)

```
WA Cloud API
  └─► POST /webhook (webhook/whatsapp.py)
        └─► NumberRouter.route() — identify sucursal
              └─► MessageRouter.handle() — conversation orchestration
                    ├─► ConversationStore.get/set() — load/save state
                    ├─► IntentParser.parse() — NLP (keyword → fuzzy → LLM)
                    │     ├─► Level 1: regex/keyword rules
                    │     ├─► Level 2: ProductMatcher (Levenshtein)
                    │     └─► Level 3: OllamaClient (local LLM)
                    ├─► ERPBridge.* — read/write ERP data
                    ├─► WAEventEmitter.emit() — publish to EventBus
                    └─► send_text() — reply to customer via WA Cloud API
```

### 2. Proactive Notification (ERP → WA → Customer)

```
ERP Core (event handler or UI action)
  └─► WhatsAppClient._post("/api/notify/*")
        └─► POST /api/notify/pedido-listo | /anticipo | /cotizacion | /send
              (auth: X-Internal-Key header)
              └─► _send() → messaging/sender.send_text()
                    └─► WA Cloud API → Customer phone
```

### 3. MercadoPago Payment Webhook

```
MercadoPago
  └─► POST /webhook/mp (webhook/mercadopago.py)
        ├─► Verify MP_WEBHOOK_SECRET
        ├─► ERPBridge — update payment status
        └─► WAEventEmitter.emit(PAYMENT_RECEIVED)
              └─► ERP EventBus
```

---

## Authentication

### WhatsApp Cloud API (outbound)
- **Token:** `WA_ACCESS_TOKEN` (env var) — Bearer token in Authorization header
- **Phone Number ID:** `WA_PHONE_NUMBER_ID` — identifies the WA Business account

### Webhook Verification (inbound)
- **Token:** `WA_VERIFY_TOKEN` — verified on GET /webhook challenge handshake

### Internal API (/api/notify/*)
- **Header:** `X-Internal-Key: <INTERNAL_API_KEY>`
- If `INTERNAL_API_KEY` is empty (dev mode), auth is skipped with a startup warning
- The ERP core sets this via `WhatsAppClient(api_key=INTERNAL_API_KEY)`

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `WA_API_VERSION` | `v21.0` | WhatsApp Cloud API version |
| `WA_PHONE_NUMBER_ID` | — | WA Business phone number ID |
| `WA_ACCESS_TOKEN` | — | WA Cloud API access token |
| `WA_VERIFY_TOKEN` | — | Webhook verification token |
| `ERP_DB_PATH` | `../pos_spj_v13.4/spj_pos_database.db` | Path to ERP SQLite database |
| `CONTEXT_DB_PATH` | `data/conversations.db` | Conversation state SQLite DB |
| `INTERNAL_API_KEY` | `""` | API key for /api/notify/* (empty = dev mode) |
| `MP_ACCESS_TOKEN` | `""` | MercadoPago access token |
| `MP_WEBHOOK_SECRET` | `""` | MercadoPago webhook HMAC secret |
| `MAX_MESSAGES_PER_MINUTE` | `15` | Rate limit per phone number |
| `MAX_FAILED_INTENTS` | `3` | Failed NLP attempts before handoff |
| `CONVERSATION_TIMEOUT_MINUTES` | `30` | Idle session timeout |
| `OLLAMA_URL` | `http://localhost:11434` | Local LLM endpoint |
| `OLLAMA_MODEL` | `deepseek-r1:8b` | Local LLM model name |
| `OLLAMA_TIMEOUT` | `15.0` | LLM request timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## NLP Pipeline (3 Levels)

```
Inbound text
  │
  ▼ Level 1 — Keyword/regex rules (O(1))
  │  Fast pattern matching for common intents:
  │  pedido, cotización, precio, estado, menú, pago, puntos, etc.
  │
  ▼ Level 2 — ProductMatcher (Levenshtein fuzzy, O(n))
  │  Searches ERP product catalog with typo tolerance
  │  Threshold: FUZZY_MATCH_THRESHOLD (default: 2 edits)
  │
  ▼ Level 3 — OllamaClient / DeepSeek-R1 (local LLM, async)
     Free-form NLP for complex or ambiguous messages
     Falls back gracefully if Ollama is unavailable
```

---

## EventBus Integration

The microservice integrates with the ERP's EventBus via `WAEventEmitter`:

- **Publishes** events when customers create orders, confirm payments, etc.
- **Consumes** ERP events (stock alerts, payroll due, etc.) to notify staff/customers via WA
- Events are persisted in `wa_event_log` table for audit trail
- Critical events (`prioridad <= 2`) are published synchronously; others async

See [WHATSAPP_EVENT_CATALOG.md](../events/WHATSAPP_EVENT_CATALOG.md) for the full event catalog.

---

## Deployment

### Development

```bash
cd whatsapp_service
cp .env.example .env
# Edit .env with real credentials
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Production

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

### ERP Path Requirement

The service expects the ERP to be at `../pos_spj_v13.4/` relative to `whatsapp_service/`. The ERP root is added to `sys.path` at startup to enable EventBus imports.

---

## Related Files

- `whatsapp_service/erp/events.py` — `WAEventEmitter`, event constants
- `whatsapp_service/erp/bridge.py` — `ERPBridge`, direct ERP DB access
- `pos_spj_v13.4/core/integrations/whatsapp_client.py` — ERP-side REST client
- `pos_spj_v13.4/core/events/event_bus.py` — ERP EventBus
- `docs/events/WHATSAPP_EVENT_CATALOG.md` — Event catalog
