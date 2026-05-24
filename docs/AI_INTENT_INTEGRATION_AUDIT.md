# AI Intent Integration Audit (WhatsApp Service)

## Estado actual del parser
- `IntentParser` usa 3 niveles: interactivo (botones/listas) → regex/patrones → LLM local (`OllamaClient`) como último recurso.
- La salida actual es `ParsedIntent(intent, confidence, action_id, products, number, raw_text, source)`.

## Intenciones actuales detectadas
- Botones/listas: `menu_action`, `select_category`, `select_product`, `select_quantity`, `confirm`, `cancel`, `select_entrega`, `select_pago`, `select_sucursal`, `add_more`, `repetir`, `estado_pedido`.
- Texto por regex/LLM: `pedido`, `cotizacion`, `cancel`, `sucursal`, `unknown` (entre otras derivadas de `patterns.py`).

## Campos de `ParsedIntent`
- Nativos: `intent`, `confidence`, `action_id`, `products`, `number`, `raw_text`, `source`.
- Actualmente los flows consumen sobre todo `intent`, `action_id`, `products` y `number`.

## Dónde se decide el flujo
- `router/message_router.py` decide por `FlowState` + `intent` y enruta a:
  - `SucursalFlow`, `RegistroFlow`, `PedidoFlow`, `CotizacionFlow`, `PagoFlow`, `MenuFlow`, `RepetirFlow`.

## Mensajes libres que hoy fallan o quedan ambiguos
- Frases largas combinadas: tiempo + sucursal + entrega + ajuste/cotización en un solo mensaje.
- Intenciones semánticas como “acepto la cotización WA-123” o “sí acepto el ajuste” dependen de reglas ad-hoc y no siempre de parser estructurado.

## Contexto disponible hoy
- `ConversationContext` aporta: estado, sucursal, cliente, carrito (`pedido_items`), tipo de entrega/dirección, fecha programada, cotización actual, tipo de número.

## Datos que NO deben enviarse a nube IA
- Tokens (`wa_meta_token`, `wa_internal_api_key`, etc.).
- Credenciales Meta/API keys internas.
- Datos financieros sensibles completos.
- Historial completo de clientes/ventas y datos de terceros.
- SQL/metadata interna del sistema.

## Plan de integración incremental (sin reemplazar parser)
1. Crear capa `whatsapp_service/ai/*` con schema + cliente IA + resolver + mapper + auditoría.
2. Mantener parser local actual como fallback obligatorio.
3. Integrar `IntentResolver` en `MessageRouter` sin cambiar flows de negocio.
4. Mapear IA → `ParsedIntent` compatible (campos extra opcionales con `getattr`).
5. Registrar auditoría en tabla `ai_intent_log` (preview truncado + hash teléfono).
6. Agregar UI ERP para activar/desactivar IA y parámetros (feature-flag por configuración).
7. Agregar tests de fallback, confianza, JSON inválido y compatibilidad.
