# SDLC-WA-011 — Mensajes y teléfonos en claro sin política de retención; bitácora de IA guarda texto y hash de teléfono reversible

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §16, §72 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`message_log` y `wa_event_log` guardan contenido y teléfono en claro sin caducidad; `ai_intent_log` guarda 160 caracteres del mensaje y un sha256 sin sal de 16 hex del teléfono, que se revierte enumerando números. Varios logs imprimen el teléfono completo. No existen `MessageRetentionPolicy` ni `SensitiveMessagePolicy` ni proceso de purga.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/state/conversation.py:125` — contenido truncado a 500 en claro
- `whatsapp_service/ai/audit_log.py:16-27` — vista previa y hash sin sal; errores tragados (`:28-29`)
- Teléfonos sin enmascarar: `whatsapp_service/middleware/rate_limiter.py:34`, `webhook/whatsapp.py:121,138`, `router/message_router.py:247`, `webhook/mercadopago.py:95`, `messaging/sender.py:267,271`, `middleware/handoff.py:39`
- Sin purga: único DELETE de origen es `pending_intents` (`router/message_router.py:287`)
- Prueba: `whatsapp_service/tests/test_redaction.py` (solo la función)

## Impacto
Privacidad: datos personales y conversaciones retenidos indefinidamente y expuestos en archivos de log.

## Objetivo
- Política de retención configurable (días de mensajes y de media) con purga programada y auditada.
- Contenido sensible enmascarado al guardar; bitácora de IA sin texto ni hash reversible.
- Ningún log del canal imprime teléfono completo.

## Alcance
- **Incluye:** Retención, redacción al guardar y en logs del microservicio.
- **No incluye:** Instalar el filtro de redacción global del ERP (SDLC-SEC-006); anonimización del cliente (SDLC-CRM-002).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-SEC-006; SDLC-CRM-002.

## Preguntas abiertas
- ¿Cuántos días se conservan mensajes y archivos de media? ¿Hay obligación de conservar alguna conversación (por ejemplo, la que originó un pedido)?
