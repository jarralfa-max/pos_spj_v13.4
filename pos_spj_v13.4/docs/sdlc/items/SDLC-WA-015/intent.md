# SDLC-WA-015 — WhatsApp emite SALE_CREATED y PAYMENT_RECEIVED como si fuera dueño, triplica eventos y ninguno de los canónicos se emite

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §55, §56 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-014

## Problema
Al crear un pedido se emiten tres eventos para la misma acción (WHATSAPP_ORDER_CREATED, WA_PEDIDO_CREADO, SALE_CREATED); el webhook de pago emite PAYMENT_RECEIVED incluso con venta 0. Esos eventos de negocio son de sus contextos. Van a `wa_event_log`, que nadie lee. De los 19 eventos canónicos del canal hay 11 definidos y ninguno se emite.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/erp/pos_notifier.py:84-86`; `webhook/mercadopago.py:151,159`; `erp/business_orchestrator.py:89,97,102,128,171,210,249,286,334`
- `whatsapp_service/domain/whatsapp/events.py:33-43` — 11 de 19, cero emisores
- `whatsapp_service/erp/events.py:43-53` — nombres duplicados
- Pruebas: `whatsapp_service/tests/test_domain_whatsapp_events.py::test_names_match_master_prompt_section_55` (solo nombres); `test_pos_notifier_dedupe::test_pos_notifier_writes_canonical_event_names` (fija la triple emisión)

## Impacto
Integración: suscriptores futuros recibirían ventas y pagos duplicados emitidos por quien no es dueño.

## Objetivo
- WhatsApp solo emite eventos `WHATSAPP_*` del canal, uno por acción, por outbox.
- Eventos de negocio solo los emiten Orders, Quotes, Payments, Delivery y Loyalty; WhatsApp los consume.

## Alcance
- **Incluye:** Catálogo y emisión de eventos del canal; retiro de re-emisiones.
- **No incluye:** Despacho de outbox de otros contextos (SDLC-ORD-002).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ORD-002.

## Preguntas abiertas
- Ninguna por ahora.
