# SDLC-PAY-023 — Permisos de pagos con proveedor incompletos: sin cobrar, cancelar, reembolsar, asignar terminal ni conciliar MP en backend

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 12.2 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 12.2 «Permisos de pagos en registro central» (`parcial`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-007

## Problema
El registro central ya tiene `POS.pago.mercado_pago`, `CAJA.terminal_pago.*`, `CAJA.reembolso.*`, `FINANZAS.conciliacion.*` y `CONFIGURACION.integracion.*`, pero faltan las capacidades de cobro, cancelación y reembolso en el proveedor, asignación de terminal, conciliación de MP y auditoría, y `CAJA.terminal_pago.conciliar_operacion` no se exige en ningún lado. El alcance por empresa y estación no está en las políticas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/security/permission_catalog.py:1-80`
- `backend/application/sales/permissions.py:61`; `backend/application/cash_register/permissions.py:31-33,86-93` (`:88` sin uso)
- `backend/application/configuracion/permissions.py:60-67`
- Prueba: `tests/architecture/test_permission_codes_contract.py`

## Impacto
Operaciones de pago sensibles sin control fino ni por ámbito.

## Objetivo
- Capacidades del documento (configurar, ver, asignar terminal, cobrar, reembolsar, cancelar, conciliar, auditar) mapeadas a la convención `MODULO.accion`, reutilizando las existentes.
- Exigidas en los casos de uso por recurso, acción y ámbito (empresa, sucursal, estación).
- Sembradas para los roles reales sin borrar asignaciones existentes; pruebas de denegación cruzada entre sucursales y empresas.

## Alcance
- **Incluye:** Catálogo, políticas, migración de siembra, pruebas.
- **No incluye:** Autorización de Integraciones en backend (SDLC-ARQ-PERM-001).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria PERM-AUD, ORG-AUD (permisos contextuales, migr. 353).

## Preguntas abiertas
- Ninguna por ahora.
