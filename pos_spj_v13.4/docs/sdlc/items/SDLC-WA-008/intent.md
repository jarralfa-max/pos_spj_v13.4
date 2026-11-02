# SDLC-WA-008 — Secretos del canal fuera del SecretStore: token de Mercado Pago y llave del ERP solo de entorno, respaldo en claro en SQLite

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §23 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El SecretStore cubre el token de Meta, verify token, app secret, llave interna y secreto del webhook de Mercado Pago, pero el token de acceso de Mercado Pago y la llave del ERP solo se leen de variables de entorno. Si no hay instancia WHATSAPP en Integraciones, el resolvedor cae a `configuraciones.wa_*` en texto plano, y la tabla legacy de números guarda `meta_token`/`twilio_token` en claro. La configuración no registra valor enmascarado, fecha de rotación ni estado.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/config/settings.py:132` — `MP_ACCESS_TOKEN` solo de entorno; usado en `webhook/mercadopago.py:77-84`, `flows/pago_flow.py:115`, `infrastructure/providers/mercadopago/gateway.py:71`
- `whatsapp_service/erp/bridge.py:149,191-195` — `ERP_API_KEY` de entorno
- `backend/infrastructure/integrations/whatsapp_credential_resolver.py:55-58` — respaldo `SELECT valor FROM configuraciones WHERE clave='wa_'+key` *(verificado directamente)*
- `migrations/m000_base_schema.py:2692` — `whatsapp_numeros.meta_token`/`twilio_token` en texto plano
- `whatsapp_service/domain/whatsapp/entities/business_account.py:24` — solo `secret_reference_id`; sin `masked_value`, `last_rotated_at`, `status`
- `whatsapp_service/infrastructure/secrets/secret_store.py:33` — con TTL=0 abre una conexión SQLite por cada lectura
- Prueba: `whatsapp_service/tests/test_secret_store.py`; `tests/integration/configuracion/test_whatsapp_credentials_regression.py` (no cubren MP ni el respaldo en claro)

## Impacto
Seguridad: tokens de cobro y de canal legibles por cualquiera con acceso al archivo de la base o al entorno del proceso.

## Objetivo
- Todo secreto del canal (incluidos token de Mercado Pago y credencial hacia el ERP) se resuelve por `SecretStoreGateway`.
- No queda lectura de `configuraciones.wa_*` ni de columnas de token en `whatsapp_numeros`.
- La configuración guarda referencia, valor enmascarado, última rotación y estado.

## Alcance
- **Incluye:** Resolución de secretos del microservicio y del resolvedor del ERP; retiro de respaldos en claro.
- **No incluye:** Filtro de redacción de logs (SDLC-SEC-006); llave maestra del almacén local (SDLC-ARQ-INST-003).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-1 (memoria); SDLC-ARQ-INST-003; SDLC-SEC-006.

## Preguntas abiertas
- ¿Alguna instalación usa hoy `configuraciones.wa_*` o tokens en `whatsapp_numeros`? Si sí, se necesita migrarlos al almacén antes de retirar el respaldo.
