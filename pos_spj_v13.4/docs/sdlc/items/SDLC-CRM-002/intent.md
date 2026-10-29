# SDLC-CRM-002 — Anonimización de cliente deja nombre y teléfono en claro fuera del maestro

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
La anonimización sólo limpia el maestro de clientes; nombre y teléfono siguen en `clientes` (legacy), conversaciones de WhatsApp y ventas. El propio código lo lista como pendiente.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/customer_privacy/use_cases/anonymize_customer_use_case.py:46-47`

## Impacto
Incumplimiento de solicitudes de privacidad (derechos ARCO).

## Objetivo
- La anonimización alcanza cada almacén de datos personales del cliente o documenta por qué uno se conserva (obligación fiscal).

## Alcance
- **Incluye:** Caso de uso de anonimización y puertos.
- **No incluye:** Unificación de maestros (CRM-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
CRM-43.

## Preguntas abiertas
- ¿Qué datos deben conservarse por obligación fiscal en ventas?
