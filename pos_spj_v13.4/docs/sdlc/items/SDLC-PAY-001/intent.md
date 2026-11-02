# SDLC-PAY-001 — Diseño de la integración Mercado Pago: TRD, flujos, modelo de datos, seguridad, UX y plan de pruebas

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 2 · Fase 18 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, sección Fase 16/17 «TRD, APPFLOW…» y Fase 18 «Instalador» (`ausente` / `no verificable`))
- **Estado:** borrador
- **Depende de:** —

## Problema
El documento exige seis documentos de diseño antes de construir (TRD, APPFLOW, DATA_MODEL, SECURITY, UX, TEST_PLAN) y no existen. Tampoco está decidido dónde viven el backend de pagos, el Access Token y la entrada pública de webhooks: hoy el token está en cada caja y en una variable de entorno del microservicio, y no hay servidor central operando. Sin esa decisión ningún ítem de construcción (PAY-007 en adelante) puede diseñarse. Además hay seis puertos de pago sin uno canónico.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/architecture/` no contiene documentos de pagos (listado en esta sesión)
- `docs/sdlc/PLAN-MAESTRO.md` «Decisiones del responsable que bloquean» punto 1 (PC anfitriona + túnel vs servidor central) — sin aprobar
- `backend/api/central_app.py:162-186` exige `SPJ_PG_DSN`; sin artefactos de despliegue (`docs/sdlc/arquitectura/matriz-brechas.md` §2/§10)
- Puertos: `backend/application/cash_register/hardware.py:61`, `backend/domain/device_management/hardware_ports.py:32`, `whatsapp_service/domain/whatsapp/payment_provider_ports.py:30`, `whatsapp_service/erp/gateways/payment_gateway.py:9`
- `installer/windows/spj_setup.iss:111-112,139-142`; `spj.spec:17-24,98-113` (servicios opcionales por equipo)

## Impacto
Bloquea toda la línea D del plan maestro. Riesgo de construir el adaptador en el lugar equivocado (cada caja) y tener que rehacerlo.

## Objetivo
- Existen `docs/architecture/MERCADO_PAGO_INTEGRATION_{TRD,APPFLOW,DATA_MODEL,SECURITY,UX,TEST_PLAN}.md` basados en la auditoría, sin duplicar documentos existentes (`FINANCIAL_TRACEABILITY_END_TO_END.md`, `ventas_official_flow.md` se actualizan donde corresponda).
- Un ADR decide: anfitrión del backend de pagos y del token, entrada pública de webhooks, puerto canónico (extender `PaymentTerminalGateway` o crear `PaymentProviderPort`), SDK `mercadopago` vs `httpx`.
- Cada fase tiene dependencias, riesgos y criterios de aceptación.

## Alcance
- **Incluye:** Documentos de diseño y ADR.
- **No incluye:** Código.

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
`docs/sdlc/PLAN-MAESTRO.md` (línea D y decisión 1); SDLC-ARQ-HYB-001 (servicio local), SDLC-SYNC-005 (central).

## Preguntas abiertas
- ¿Dónde vive el backend de pagos y el Access Token: PC anfitriona de sucursal (plan maestro, decisión 1), servidor central o, temporalmente, cada caja?
- ¿Entrada pública de webhooks: ngrok, Cloudflare Tunnel o servidor central?
- ¿Se usa Mercado Pago hoy en producción (POS manual y/o WhatsApp) y con cuántas cuentas cobradoras (una por empresa o por sucursal)?
