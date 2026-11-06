# SDLC-PAY-012 — Terminales Point Smart: sin descubrimiento, vinculación a estación, modo PDV ni exclusión entre estaciones

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 4.1 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 4.1 «Terminales Point…» (`ausente`, sólo dominio de dispositivos))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-009, SDLC-ARQ-TERM-001, SDLC-ARQ-HYB-001

## Problema
El inventario de dispositivos ya modela una terminal de pago asignable a una estación, pero no hay forma de listar las terminales de la cuenta, vincular una Point a una estación SPJ y a una caja de Mercado Pago, verificar o activar modo PDV, detectar terminal ocupada, ni impedir que dos estaciones envíen órdenes a la misma terminal. Caja tiene además su propia tabla `pos_terminals`, una tercera identidad.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/device_management/enums.py:78,93`; `workstation_device_assignment.py:23`; `payment_terminal_profile_policy.py:14`
- `backend/infrastructure/db/repositories/cash_register/repositories.py:104,116` — `pos_terminals`
- `frontend/desktop/modules/configuracion/dialogs/device_dialogs.py:19`; `cash_register_routes.py:137` — las terminales se administran en Caja
- Prueba: unitarias de la política de perfil

## Impacto
Sin vinculación no hay cobro Point; sin exclusión, dos cajeros pueden cobrar en la misma terminal.

## Objetivo
- Listar terminales autorizadas y vincularlas a estación SPJ y caja MP (sin confundirla con el turno de Caja), con permiso y auditoría.
- Verificar estado operativo y modo PDV; reasignación y revocación controladas.
- Una terminal no acepta una orden mientras otra esté activa (coordinación según PAY-001/HYB-001).
- Una sola identidad de terminal de pago (se decide cuál de las existentes).

## Alcance
- **Incluye:** Gestión de terminales en Caja, mapeos, exclusión, pruebas.
- **No incluye:** Diálogo de cobro (PAY-013).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-ARQ-TERM-001 (identidad de terminal fragmentada), SDLC-ARQ-HYB-001 (servicio local).

## Preguntas abiertas
- ¿Cuántas Point Smart hay y en qué sucursales/cajas? tengo una por sucursal¿Ya están en modo PDV? aun no 
