# SDLC-WA-035 — No hay forma de darse de baja por WhatsApp y el control de consentimiento falla abierto

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §45, §46 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-034

## Problema
STOP, BAJA o CANCELAR PROMOCIONES no se reconocen en el camino vivo (OPT_OUT solo existe en el resolvedor canónico sin uso). El control antes de enviar mira solo `WHATSAPP=WITHDRAWN` sin distinguir transaccional de marketing, deja pasar el envío ante cualquier error y abre una conexión del bridge por envío que nunca cierra. `ConsentService.record_opt_out` no tiene llamador y escribe por repositorio evitando `WithdrawConsentUseCase`. No hay auditoría ni confirmación al usuario.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/messaging/sender.py:114-158` — `except` → "envío continúa" *(verificado directamente)*; `:131-133` conexión por envío
- `whatsapp_service/application/consent_service.py:31,47`; `infrastructure/erp_clients/consent_client.py:19-21,91-106`
- `backend/application/customer_privacy/use_cases/consent_use_cases.py:136`; `backend/domain/customer_privacy/enums.py:9-17`
- `backend/application/loyalty/use_cases/birthday_use_cases.py:304` — `has_marketing_consent=True` fijo (hoy no envía WhatsApp)
- Pruebas: `whatsapp_service/tests/test_sender_consent_gate.py`, `test_consent_service.py`, `test_consent_client.py`

## Impacto
Legal y privacidad: se pueden mandar mensajes a quien pidió no recibirlos; no hay prueba de cumplimiento.

## Objetivo
- Palabras de baja procesadas por un caso de uso que registra la revocación, detiene marketing, conserva lo legalmente permitido, audita y confirma al cliente.
- El control distingue categorías y, ante error, no envía marketing (falla cerrado).
- Escritura de consentimiento por los casos de uso de Privacidad.

## Alcance
- **Incluye:** Opt-out y control de consentimiento del canal.
- **No incluye:** Consentimiento de otros canales del ERP.

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-14 (memoria); CRM-9.

## Preguntas abiertas
- ¿Qué mensajes se consideran transaccionales y siguen permitidos tras una baja (pedido listo, pago recibido, ajuste de peso)? ¿Qué palabras exactas cuentan como baja?
