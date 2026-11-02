# SDLC-WA-022 — Conversación viva como cadena de if/elif sobre estados legacy; el timeout borra el carrito sin avisar

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §14, §26, §31 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019

## Problema
El camino vivo despacha por prefijo de `FlowState` y por `action_id` en cada flujo; el contexto se guarda como JSON sin versión ni validación en otra base, se pierde en silencio si no se puede leer, y a los 30 minutos se reinicia sin decir nada al cliente. `ConversationEngine` y `ConversationStateMachine` (12 estados, contexto versionado de solo referencias) existen sin uso. Hay código muerto: `delivery_flow.py` no se importa, el menú secundario nunca se envía, los flujos se construyen sin horario, orquestador ni recordatorios.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/router/message_router.py:137-155,189-205`; `flows/pedido_flow.py:36-63,179-353`; `flows/menu_flow.py:25-105`
- `whatsapp_service/models/context.py:16-40`; `state/conversation.py:44-55,65-79`
- Canon: `whatsapp_service/application/conversation_engine.py:37-96`; `domain/whatsapp/services/conversation_state_machine.py:22-91`; `domain/whatsapp/entities/conversation_context.py:16-43`
- Pruebas: `whatsapp_service/tests/test_conversation_engine.py`, `test_conversation_state_machine.py` (canon); `test_conversation_quote_context.py` (vivo, falla hoy)

## Impacto
Clientes pierden su pedido a medias; cada cambio de flujo es frágil.

## Objetivo
- El trabajador del inbox conduce la conversación con el motor canónico: estado, datos faltantes, confirmación, cancelación, timeout con aviso y reinicio.
- Contexto versionado y validado con solo referencias.
- Flujos muertos retirados.

## Alcance
- **Incluye:** Motor y contexto en el camino vivo.
- **No incluye:** Resolución de intención (SDLC-WA-023); textos (SDLC-WA-025).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-7 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
