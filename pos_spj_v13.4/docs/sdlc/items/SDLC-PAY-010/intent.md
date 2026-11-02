# SDLC-PAY-010 — No hay webhook central ni inbox durable: notificaciones de Mercado Pago no verificadas ni recuperables

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 7 · Fase 16.3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 7 «Endpoint webhook central», «Verificador de firma del backend», «Persistir antes de 200…» (`ausente` / `defectuoso`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-007, SDLC-PAY-001, SDLC-WA-002

## Problema
El backend no tiene receptor de webhooks. Su verificador `x-signature` existe pero tiene tres defectos (sin ventana de `ts`, `data.id` leído de una cabecera inventada, cabeceras sensibles a mayúsculas) y nadie lo usa. El único receptor real vive en el microservicio y responde 200 sin persistir, sin límite de tamaño ni deduplicación por notificación.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/routers/` — sólo analytics, devices, driver_logistics, mobile_logistics, sync
- `backend/infrastructure/integrations/webhook_signature_verifier.py:24-25,47-60`
- `backend/domain/integrations/entities/webhook_endpoint.py:30-73` — `mark_received` nunca se llama
- `whatsapp_service/webhook/mercadopago.py:35,61-62,78-79,86-87,166-169`
- Patrones reutilizables: `backend/api/routers/sync.py:33,68`; `backend/application/sync/replication_outbox.py:48,58-69`; inbox de WhatsApp `sqlite_inbox_repository.py`
- Prueba: `tests/unit/integrations/test_webhook_endpoint_and_verifier.py:120` (`ts` fijo)

## Impacto
Aprobaciones perdidas o aceptadas sin verificar; replays posibles.

## Objetivo
- Ruta de webhook en el backend elegido por PAY-001, siguiendo el estándar real de routers, con firma verificada (ventana de tiempo, `data.id` del query, cabeceras sin distinción de mayúsculas), validación de ambiente/aplicación/cuenta, límite de tamaño y parsing estricto.
- El evento se guarda durablemente antes de responder 200; deduplicación por id de notificación; worker con backoff, dead-letter y métricas.
- El webhook sólo dispara una consulta autorizada al recurso remoto y compara monto, moneda, referencia y cuenta antes de cambiar la intención.
- Pruebas: firma inválida, replay, duplicado, fuera de orden, manipulado.

## Alcance
- **Incluye:** Router, verificador, inbox, worker, pruebas de seguridad.
- **No incluye:** Retiro del webhook del microservicio (SDLC-WA-001/PAY-025).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-WA-001 (ampliado), SDLC-WA-002, SDLC-WA-006 (workers que nunca corren).

## Preguntas abiertas
- Ninguna por ahora.
