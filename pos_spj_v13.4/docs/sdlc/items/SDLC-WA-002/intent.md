# SDLC-WA-002 — Webhooks de WhatsApp y pagos aceptan peticiones sin firma si falta APP_ENV

- **Prioridad:** P0
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`APP_ENV` tiene por defecto `development`; en ese modo ambos webhooks omiten la verificación de firma, se permiten escrituras SQLite y se salta la validación de secretos de producción. Un despliegue que olvide la variable queda abierto. Aparte, el anti-replay trata el `ts` de MercadoPago como milisegundos y una prueba lo fija como contrato; si el proveedor envía segundos, toda notificación legítima se rechaza (no verificado contra documentación).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/config/settings.py:166` — default `development`
- `whatsapp_service/webhook/whatsapp.py:85-89`, `whatsapp_service/webhook/mercadopago.py:53-57` — omiten firma fuera de producción
- `whatsapp_service/main.py:91` — validación de secretos sólo en producción
- `whatsapp_service/middleware/hmac_validator.py:57-63` y `whatsapp_service/tests/test_mercadopago_webhook_signature.py:28-29` — `ts` en ms (**no verificado** contra el proveedor)

## Impacto
Seguridad: cualquiera puede inyectar mensajes o 'pagos' falsos en un despliegue mal configurado.

## Objetivo
- Sin `APP_ENV` explícito el servicio se comporta como producción (fail-closed) o se niega a arrancar.
- El modo desarrollo requiere opt-in explícito y se registra al arrancar.
- La unidad de `ts` se confirma contra la documentación oficial y la prueba refleja el formato real.

## Alcance
- **Incluye:** Configuración y validadores de firma del microservicio.
- **No incluye:** Matching de pagos (SDLC-WA-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
WA-0..20 (memoria); `docs/audits/WHATSAPP_PHASE0_SAFETY_MAP.md`.

## Preguntas abiertas
- ¿Hay hoy algún despliegue del microservicio sin `APP_ENV=production`?
