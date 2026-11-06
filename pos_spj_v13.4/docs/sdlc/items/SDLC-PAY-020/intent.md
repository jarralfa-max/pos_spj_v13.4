# SDLC-PAY-020 — Reembolso vía API de Mercado Pago con estados, parciales y eventos tardíos

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 15 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 15 «Reembolso vía API, parcial, estados, tardíos» (`ausente`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-006, SDLC-PAY-009, SDLC-PAY-010

## Problema
No existe reembolso por API. Tras PAY-006 el reembolso será manual con estados; falta solicitarlo al proveedor, consultar su estado, manejar rechazos, duplicados y eventos tardíos, y revertir beneficios según política.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- Ninguna llamada a reembolso en `backend/` ni `whatsapp_service/` (búsqueda en esta sesión)
- Política reutilizable: `backend/domain/sales/services/refund_service.py:59-100`; autorización `return_use_cases.py:84-90,205-211`; puntos `sales_events.py:58,91,203`
- Prueba: ninguna

## Impacto
Reembolsos lentos y propensos a error humano.

## Objetivo
- Reembolso total y parcial (cuando la modalidad lo admita) con autorización de supervisor, idempotente y con estados solicitado → procesando → aprobado/rechazado.
- Cancelar el diálogo nunca crea un reembolso remoto; «recibido» no es «finalizado».
- Pruebas: parcial seguido de otro parcial, rechazo, duplicado, tardío.

## Alcance
- **Incluye:** Caso de uso, adaptador, estados, pruebas.
- **No incluye:** Contracargos (PAY-021).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- Ninguna por ahora.
