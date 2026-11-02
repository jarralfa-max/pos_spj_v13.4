# SDLC-WA-020 — Selección de producto por WhatsApp falla con IDs UUIDv7: int() descarta el producto en silencio

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §30, §34 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Los productos del catálogo canónico tienen id UUIDv7, pero el router, el resolvedor de IA y el flujo de pedido hacen `int(prod["id"])` o `int(action_id.split("_")[1])`. La conversión lanza y el producto se descarta o la selección de lista falla. Las pruebas usan ids enteros y lo ocultan.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/router/message_router.py:337`; `ai/intent_resolver.py:136` *(verificado directamente)*
- `whatsapp_service/flows/pedido_flow.py:100` — `int(intent.action_id.split("_", 1)[1])` *(verificado directamente)*
- `whatsapp_service/parser/product_matcher.py:51-57` — ids del maestro canónico (PROD-22)
- `whatsapp_service/application/confirm_order_use_case.py:61` — `int(order["venta_id"])`
- Pruebas con ids enteros: `tests/test_wa_flows.py`; `whatsapp_service/tests/test_message_router_intent_resolver_integration.py`

## Impacto
Clientes: no pueden agregar productos al pedido por lista ni por texto libre.

## Objetivo
- Ningún `int()` sobre identidades en el canal (prueba de arquitectura).
- Pruebas con ids UUIDv7 reales para lista y texto libre.

## Alcance
- **Incluye:** Router, resolvedor, flujo de pedido y caso de uso de confirmación.
- **No incluye:** Precio de registro (SDLC-WA-021).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ORD-005 (mismo patrón en la captura de escritorio).

## Preguntas abiertas
- Ninguna por ahora.
