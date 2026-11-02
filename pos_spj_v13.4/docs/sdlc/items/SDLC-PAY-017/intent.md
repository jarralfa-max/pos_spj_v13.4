# SDLC-PAY-017 — Sin política offline para cobros electrónicos ni coordinación entre equipos

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 8 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 8 «Política offline…» (`defectuoso`) y «Coordinación central…» (`ausente`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-008, SDLC-ARQ-HYB-002, SDLC-ARQ-HYB-001

## Problema
Todo es SQLite local, así que hoy el cajero puede registrar un cobro MP «confirmado» sin red. No hay regla que impida crear órdenes sin backend, que mantenga estados inciertos ni que evite que dos equipos confirmen, cancelen o reembolsen la misma operación.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py:107,194-196,260`
- `docs/sdlc/arquitectura/matriz-brechas.md` §8/§9 — sin servicio local ni política degradada
- Prueba: ninguna

## Impacto
Cobros inventados offline; confirmaciones concurrentes.

## Objetivo
- Sin comunicación con el backend autorizado no se crean órdenes ni se confirman cobros; el efectivo sigue según reglas offline existentes; la UI no se bloquea.
- Al reconectar: identificar intenciones, consultar, deduplicar, confirmar una sola vez, publicar eventos.
- Confirmar/cancelar/reembolsar una intención es exclusivo entre equipos.
- Pruebas: pago aprobado durante caída de internet, dos equipos confirmando.

## Alcance
- **Incluye:** Política, detector de conectividad de pagos, recuperación, pruebas.
- **No incluye:** Construir el servicio local (SDLC-ARQ-HYB-001).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-ARQ-HYB-001/002.

## Preguntas abiertas
- ¿Se permite cobrar con Point si la caja no tiene internet pero la terminal sí (la orden la crea el backend)?
