# SDLC-ORD-011 — Política de avisos de Pedidos fija en código, sin ajuste por sucursal

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/refactor/ORD-30_validacion_final.md` → "Pendiente" §6 (motor de políticas de notificación configurable por sucursal, ORD-26, "si el negocio lo pide"). Re-verificado (`/sdlc-plan` Modo B, 2026-10-31).
- **Estado:** borrador
- **Depende de:** SDLC-ORD-006

## Problema
Qué evento manda mensaje al cliente, con qué texto y qué evento genera alerta interna (y a qué roles) está fijo en el código. Una sucursal no puede apagar un aviso, cambiar un texto ni elegir destinatarios. ORD-26 lo dejó así a propósito, condicionado a que el negocio lo pidiera.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- `backend/domain/orders_delivery/policies/notification_policy.py:10-15`: "Deliberately NOT a full configurable/DB-backed rules engine ... an admin-configurable version is a future phase's job if the business actually asks for per-branch overrides."
- `notification_policy.py:22-27` (`_CUSTOMER_MESSAGE_TEMPLATES` en código) y `:38-41` (`_INTERNAL_ALERT_EVENTS`).
- `backend/application/orders_delivery/use_cases/dispatch_use_cases.py:218-219`: roles `("admin", "gerente")` fijos en la llamada.
- Referencia del patrón configurable: Caja CASH-20 (`cash_alert_rules`/`cash_notification_jobs`, citado en la misma docstring). Su estado vivo no se comprobó: **no verificado**.

## Impacto
Bajo mientras el negocio no lo pida. Los roles fijos por texto (`"admin"`, `"gerente"`) repiten el patrón que SDLC-INV-008 señala para las alertas de stock (destinatarios por texto de rol legacy, fuera del RBAC).

## Objetivo
- Si el responsable lo aprueba: los avisos de Pedidos (activar o desactivar, plantilla, destinatarios por permiso y no por texto de rol) se configuran por sucursal desde Pedidos → Configuración, sin una segunda pantalla en Configuración (regla de la memoria). Por defecto se comporta igual que hoy.
- Si no lo aprueba: el ítem se descarta con la decisión registrada y solo se cambian los roles fijos por un permiso (alinear con SDLC-INV-008).

## Alcance
- **Incluye:** Decisión; si se aprueba, configuración por sucursal y destinatarios por permiso.
- **No incluye:** Reintentos (SDLC-ORD-006) ni el motor de alertas de otros módulos.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Configuración no duplica módulos.

## Trabajo previo relacionado
ORD-26; CASH-20; SDLC-INV-008.

## Preguntas abiertas
- ¿El negocio necesita ajustar los avisos de Pedidos por sucursal? Si no, se descarta y se queda solo el cambio de roles a permiso.
