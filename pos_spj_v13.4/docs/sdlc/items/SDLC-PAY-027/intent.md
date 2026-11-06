# SDLC-PAY-027 — Sin suite de fallos y concurrencia para pagos (20 escenarios del documento)

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 16.4 · Fase 19 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 16.4 «20 escenarios de fallo y concurrencia» (`ausente`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-011, SDLC-PAY-013, SDLC-PAY-016

## Problema
No existe ninguna prueba de terminal compartida, timeout de creación, respuesta perdida, webhook duplicado/fuera de orden/nunca recibido, reinicio del POS o backend durante el pago, caída de PostgreSQL, cambio de importe o de terminal durante un pago pendiente, ni instalación/actualización sin pérdida de datos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- Búsqueda en `tests/` sin pruebas de esos escenarios (subagentes de integraciones y UI)
- Las pruebas «pendiente/webhook» de MP son legacy y no colectan (línea base de la auditoría)

## Impacto
Sin evidencia de que los timeouts no causen doble cobro (criterio de aceptación §19).

## Objetivo
- Los 20 escenarios de §16.4 automatizados con proveedor falso, sin pagos reales.
- Corren en el segmento de CI correspondiente.

## Alcance
- **Incluye:** Pruebas de integración y concurrencia.
- **No incluye:** Sandbox de MP (manual).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-CORE-007 (segmento de integración que no colecta).

## Preguntas abiertas
- Ninguna por ahora.
