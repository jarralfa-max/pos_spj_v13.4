# SDLC-PAY-028 — Pruebas y docstrings de Mercado Pago apuntan a código legacy eliminado

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 1.5 · Fase 16 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.5 «Imports a legacy eliminado» (`legacy`))
- **Estado:** borrador
- **Depende de:** —

## Problema
Al menos nueve archivos de prueba de pagos importan o leen `core/`, `services/` o `modulos/`, eliminados el 2026-09-10 (`47fb64cb`): fallan o no colectan, y dos están permitidos a propósito en la lista de excepciones de arquitectura. Dos docstrings afirman que la integración legacy de MP existe.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- Línea base: 6 fallan, 4 no colectan (`tests/test_mercado_pago_pending_flow.py`, `tests/test_mercado_pago_webhook_confirmation.py`, `tests/test_fase6_mercadopago_cleanup.py`, `tests/test_payment_method_normalization.py`, `tests/test_phase5_payment_policy.py`, `tests/integration/integrations/test_mercadopago_credential_resolver.py:83,98,121`)
- También `tests/test_fase8_no_silent_passes.py:7-14`, `tests/test_fase4_payment_mapping.py:3`, `tests/test_financial_core_enforcement.py:486-545`
- `tests/architecture/allowlists.py:105,123`
- Docstrings: `backend/application/sales/use_cases/payment_use_cases.py:15-23`; `backend/infrastructure/integrations/mercadopago_credential_resolver.py:14`

## Impacto
Ruido en CI y falsa sensación de cobertura del flujo pendiente/webhook.

## Objetivo
- Cada prueba se elimina (si cubre código que ya no existe) o se reescribe contra el contexto canónico, con decisión registrada por archivo.
- Se limpian las excepciones de la lista y los docstrings.

## Alcance
- **Incluye:** Pruebas legacy, allowlist, docstrings.
- **No incluye:** Código de producción.

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
SDLC-CORE-005 (código muerto), SDLC-CORE-011.

## Preguntas abiertas
- ¿Se borran las pruebas legacy o se reescriben las que describen comportamiento deseado (pendiente, webhook)?
