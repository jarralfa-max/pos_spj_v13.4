# SDLC-PAY-015 — QR dinámico: no existe en el diálogo de cobro ni en el monitor del cliente

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 6 · Fase 13.2 · 13.3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 6 «QR dinámico» (`ausente`), Fase 13.3 «Monitor del cliente» (`parcial`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-014, SDLC-PAY-013

## Problema
Ni el diálogo ni el monitor del cliente pueden mostrar un QR. El monitor ya muestra importe, confirmación y marca configurable, y el backend ya genera matrices QR para etiquetas, pero no hay widget QR de escritorio.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/customer_display_window.py:61,137-144,336-349`; empuje `sales_pos_presenter.py:606-649`
- `backend/infrastructure/printing/container_label_renderer.py:34` `qr_matrix()`; `qrcode==8.2` en release
- `frontend/desktop/modules/fidelidad/cards/card_preview.py:85-91` — QR falso
- Prueba: `tests/unit/sales_pos/test_customer_display_window.py:57,76`

## Impacto
Cliente presencial sin opción de pagar con su teléfono.

## Objetivo
- QR del Checkout de la intención activa en el diálogo y en el monitor, con importe, referencia y vencimiento.
- Regenerar la vista no duplica órdenes; el QR se invalida tras pago, cancelación o expiración; el estado se refresca desde el backend.
- Escanear no equivale a aprobado.
- Se distingue QR de Checkout de QR nativo de MP (no se presentan como equivalentes).

## Alcance
- **Incluye:** Widget QR reutilizable, diálogo, monitor, pruebas.
- **No incluye:** QR nativo de Mercado Pago (se evalúa en PAY-001).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- Ninguna por ahora.
