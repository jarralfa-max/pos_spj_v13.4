# SDLC-WA-009 — Llamadas WhatsApp→ERP con X-API-Key estática, sin HMAC ni identidad de servicio

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §53, §54 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003, SDLC-WA-008

## Problema
El ERP firma sus llamadas al microservicio con HMAC, timestamp y nonce, pero en sentido contrario el bridge manda una cabecera `X-API-Key` fija, sin firma, timestamp, nonce, `service_id` ni `correlation_id`. La caché de nonces del lado WhatsApp vive en memoria del proceso (se pierde al reiniciar y no sirve con varios workers), no hay rotación con dos llaves ni `kid`, y la identidad `WHATSAPP_CHANNEL_SERVICE` está definida y no se usa: el ERP no tiene cuenta de servicio con permisos mínimos para el canal.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/erp/bridge.py:191-195` — cabecera estática
- `whatsapp_service/middleware/service_auth.py:43` — `WHATSAPP_CHANNEL_SERVICE = "whatsapp-channel"` sin uso; `:50-54` nonces en memoria; `:57-142` verificación ERP→WA correcta
- `backend/infrastructure/integrations/whatsapp_client.py:73-83,147-163` — el ERP sí firma
- Sin identidad de servicio en `backend/` ni `migrations/` (búsqueda sin resultados)
- Prueba: `whatsapp_service/tests/test_service_auth.py` (solo ERP→WA)

## Impacto
Seguridad: cuando exista el contrato del ERP (SDLC-WA-003), cualquiera con la llave fija podría operar como el canal; no hay forma de revocar o auditar al canal como actor.

## Objetivo
- Las llamadas WA→ERP van firmadas (HMAC con timestamp, nonce, `service_id`, `correlation_id`) y el ERP las verifica.
- Existe una identidad de servicio del canal, revocable y rotable, con permisos mínimos y auditada como actor.
- La protección anti-replay sobrevive a reinicios.

## Alcance
- **Incluye:** Firma y verificación WA→ERP; identidad de servicio; almacén persistente de nonces.
- **No incluye:** Definir los endpoints del ERP (SDLC-WA-003).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-1 (memoria); SDLC-SEC-005 (nonce por proceso, mismo patrón en el ERP).

## Preguntas abiertas
- ¿La identidad de servicio vive en `usuarios` con un rol técnico o en una tabla propia de identidades de servicio?
