# SDLC-SYNC-005 — Ninguna estación replica al central: transporte nunca configurado y sin planificador

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-002, SDLC-SYNC-003, SDLC-SYNC-004

## Problema
`cash_register_factory` lee `composition_root.cash_sync_transport`, que nadie asigna, y cae siempre a `MissingReplicationTransport`; `HttpReplicationTransport` sólo se construye en pruebas. El único disparador es manual (Caja) y no hay timer. Cada ciclo manual suma un intento y tras `MAX_ATTEMPTS=25` todos los sobres pasan a DEAD.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/desktop/cash_register_factory.py:492-496,1238-1254`
- `backend/application/sync/replication_outbox.py:48,240-242`; `replication_repository.py:147`

## Impacto
La arquitectura offline-first no sincroniza; además, pulsar 'sincronizar' sin transporte quema intentos hasta matar los sobres.

## Objetivo
- Sin transporte configurado, un ciclo no consume intentos.
- Con transporte configurado, un trabajador periódico replica y reporta estado.
- Configuración del transporte desde Integraciones/instalación (sin secretos en código).

## Alcance
- **Incluye:** Composición del transporte, planificador, contabilidad de intentos.
- **No incluye:** Correcciones de pérdida de datos (SYNC-002/003/004), que deben ir antes.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Pipeline híbrido; `docs/sdlc/inputs/requisitos-arquitectura.md`.

## Preguntas abiertas
- ¿Ya hay un servidor central (Oracle Always Free) listo para recibir tráfico real?
