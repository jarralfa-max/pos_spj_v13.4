# SDLC-PAY-029 — Runbook operativo de Mercado Pago en español

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 17 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 17 «Runbook operativo» (`ausente`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-013, SDLC-PAY-014, SDLC-PAY-019, SDLC-PAY-022

## Problema
No existe documentación operativa: registro de la aplicación, credenciales, sandbox/producción, vinculación Point, modo PDV, webhooks y HTTPS, multi-sucursal, permisos, pruebas de cobro, cierre, conciliación, reembolsos, recuperación, rotación de secretos, desconexión e incidencias.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/` sin runbook de pagos (listado en esta sesión)

## Impacto
Puesta en marcha dependiente de quien construyó la integración.

## Objetivo
- Runbook en español sin secretos reales, validado contra la implementación entregada.

## Alcance
- **Incluye:** Documentación.
- **No incluye:** —

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- Ninguna por ahora.
