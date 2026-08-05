# CASH-6 — Cajas, cajones y terminales

Fecha: 2026-08-03  
Estado: `IMPLEMENTED` en arquitectura canónica; navegación legacy aún no sustituida.

## Entregado

- Alta UUIDv7 de cajas, cajones y terminales.
- Activación y bloqueo con permiso granular, scope de sucursal y motivo auditado.
- Asignación/reasignación de cajones y terminales a cajas de la misma sucursal.
- Repositorio canónico sin commits propios.
- Mutaciones atómicas: dispositivo, auditoría, evento y outbox.
- Idempotencia protegida por `operation_id` del outbox/evento.
- `CashHardwareGateway` desacoplado de USB/serial/red y stub determinista para pruebas.
- Diagnóstico de hardware auditado incluso cuando el dispositivo está desconectado.
- QueryService y página PyQt canónica para Cajas, Cajones y Terminales.

## Seguridad

- `CASH_REGISTER_MANAGE`, `CASH_REGISTER_ACTIVATE`, `CASH_REGISTER_BLOCK`.
- `CASH_DRAWER_MANAGE`, `CASH_TERMINAL_MANAGE`.
- `CASH_HARDWARE_DIAGNOSE`.
- Toda operación revalida permiso y alcance en backend.

## UI

La página usa `PageHeader`, `StandardTable` y factories de botones. Emite señales de acción; no importa repositorios, conexiones o drivers y no contiene SQL, commits, estilos inline ni lógica de estado.

## Tests

- Alta de caja/cajón/terminal.
- Bloqueo y reactivación.
- Reasignación dentro de sucursal.
- Igualdad entre auditorías, eventos y outbox.
- Hardware desconectado por gateway y diagnóstico auditado.
- Guardrail UI sin base de datos ni hardware directo.
