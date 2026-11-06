# SDLC-PAY-013 — Cobro con Point desde el diálogo estándar: el diálogo es modal y síncrono, sin estados ni recuperación

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 4.3 · Fase 13.1 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 13.1 «Flujo Point en el diálogo» (`ausente`) e «Indicador de terminal» (`parcial`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-008, SDLC-PAY-011, SDLC-PAY-012

## Problema
El diálogo de cobro es modal y ejecuta todo en un clic; sólo conoce los estados `PENDING` y `FAILED`. Una espera de terminal congelaría el POS. La barra del cajero ya tiene un indicador «Terminal» pero lo oculta, y la salud sólo dice «configurado/falta».

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py:66,331-383`; `sales_pos_workspace.py:542`
- `frontend/desktop/modules/sales_pos/components/cashier_bar.py:29,71-77`
- `backend/application/sales/queries/device_health_query_service.py:37`; patrón `ScaleMonitor`
- Prueba: `tests/unit/test_sales_pos_visual_validation.py:65,94-143` (estructural); diálogo de pago sin captura

## Impacto
Cajero: sin flujo integrado; riesgo de congelar la caja o de cobrar dos veces al reintentar.

## Objetivo
- Mercado Pago Point dentro del diálogo estándar: terminal, importe, conexión, estados (preparando, esperando terminal, esperando tarjeta, procesando, verificando, aprobado, rechazado, cancelado, expirado, desconocido, error), cancelación controlada, reintento seguro y recuperar estado.
- La espera no bloquea la UI; HTTP 201 nunca equivale a aprobado.
- Indicador de terminal visible con estado real.
- Layout del POS y golden masters preservados en 1366×768 y 1920×1080, claro y oscuro.

## Alcance
- **Incluye:** Diálogo, presentador, barra del cajero, pruebas UI.
- **No incluye:** QR (PAY-015).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria UI Design System (MessageDialog).

## Preguntas abiertas
- Ninguna por ahora.
