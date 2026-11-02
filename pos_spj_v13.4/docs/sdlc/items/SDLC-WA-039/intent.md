# SDLC-WA-039 — Reintentos sin clasificación de errores, dead letter sin escritor y límite de mensajes solo por teléfono en memoria

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §59, §60, §61 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019

## Problema
El outbox reintenta todo (también `opted_out`) con espera fija, sin multiplicador ni jitter, y sin lista de errores reintentables. `whatsapp_dead_letter` no tiene escritor: DEAD_LETTER es solo un estado de fila. El límite de mensajes es por teléfono, en memoria, crece sin tope, y lo que corta se descarta con 200 sin registro. No hay límite saliente, por número, por IP ni política de spam.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/domain/whatsapp/entities/outbox_message.py:31-46`; `infrastructure/providers/meta_cloud_api/gateway.py:196-200`
- `backend/infrastructure/db/schema/whatsapp_schema.py:236-247`; `whatsapp_service/application/diagnostics_service.py:118` (único lector)
- `whatsapp_service/middleware/rate_limiter.py:18-39`; `webhook/whatsapp.py:24,120-122`
- Pruebas: `whatsapp_service/tests/test_outbound_dispatcher.py`; `tests/test_wa_phase9_regression.py::test_webhook_rate_limit_blocks_processing`

## Impacto
Mensajes fallidos perdidos sin rastro; reintentos inútiles contra clientes dados de baja; clientes legítimos bloqueados sin motivo registrado.

## Objetivo
- Política de reintento configurable con errores no reintentables (payload inválido, consentimiento revocado, número bloqueado, plantilla rechazada).
- Todo fallo definitivo queda en dead letter con resolución auditada.
- Límites entrantes y salientes por identidad, número, IP, cuenta y plantilla, persistentes y con motivo registrado.

## Alcance
- **Incluye:** Reintentos, dead letter, rate limiting.
- **No incluye:** —

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-17 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
