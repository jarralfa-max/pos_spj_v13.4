# 07 — Análisis de brechas y estrategia incremental

## Brechas frente al objetivo (§2 del prompt)

| Capacidad | Hoy | Brecha | Prioridad |
|---|---|---|---|
| SQLite local offline | Sí (POS, Caja, Inventario sin red) | Atomicidad dependiente de la conexión (R-01); FK apagadas (R-02) | P0 |
| Outbox transaccional | ~30 outbox por contexto, misma transacción con la conexión del escritorio | Garantía formal independiente de la conexión | P0 |
| Motor de replicación | 3 parciales, sin transporte | Uno solo, con transporte HTTPS, backoff con jitter, dead-letter, checkpoints y telemetría | P0 |
| Contrato de evento versionado | Cada outbox tiene su forma; CASH-19 define `SyncEnvelope` (`envelope_id`, `sequence_no`, `aggregate_version`, `event_name`, `operation_id`, `entity_id`, `payload`) | Faltan `schema_version`, `branch_id`, `workstation_id`, `actor_id`, `correlation_id`, `causation_id` y la referencia de autorización | P0 |
| PostgreSQL central | Rama PG reservada (`NotImplementedError`) | Fábrica de conexión, esquema base PG, carril de migraciones, repositorios PG | P1 |
| Inbox central | `inventory/sync/event_ingestor.py` (sólo Inventario) | Generalizar: unicidad por `(installation_id, operation_id)`, aplicación transaccional, comprobante | P1 |
| API de sincronización | Ninguna ruta | `/api/v1/sync/events` (lote), `/acks`, `/changes?cursor=`, `/status`, `/masters`, `/conflicts` | P1 |
| Credencial de estación | Identidad local (`installation`, `workstations`); credencial móvil | Credencial emitida por el central, rotación y baja de estación | P1 |
| Datos maestros desde el central | Catálogo, precios, permisos y usuarios locales | Distribución versionada con autoridad central (matriz en Fase 1) | P2 |
| Conflictos visibles | 4 tablas | Una vista operativa común y estados en la UI | P2 |
| BI corporativo | Sólo local | Consultas multi-sucursal en el central | P3 |
| WhatsApp | Archivo SQLite directo | Modo API obligatorio | P2 |
| Respaldo PG | Ninguno | `pg_dump` cifrado, restauración probada, RPO/RTO medidos | P2 |
| Instalador | Firmado, con rollback | Endpoint central, aprovisionamiento, diagnóstico | P2 |
| Pruebas PG reales | Ninguna (sin PG en el entorno) | PostgreSQL en desarrollo y en CI | P1 |

## Orden de ejecución propuesto (ajusta el §15 del prompt por dependencias reales)

1. **Slice 0 — Base transaccional local (P0).** Las UoW abren su propia transacción, se activan las FK en
   la conexión del escritorio y hay pruebas de contrato con las dos conexiones. *Sin esto, nada de lo
   siguiente es seguro.*
2. **Slice 1 — Contrato de evento de sincronización.** Se extiende `SyncEnvelope` de CASH-19 con los campos
   faltantes, con versión y serialización Decimal/UUIDv7, y se fija con pruebas unitarias.
3. **Slice 2 — Motor de replicación único.** Se generaliza CASH-19 a un `ReplicationOutbox` que toma de los
   outbox de contexto. Inventario y Mermas migran a él y se retiran sus motores. Transporte en memoria
   primero, HTTPS después.
4. **Slice 3 — PostgreSQL mínimo.** Rama PG de `create_connection_factory` (psycopg 3), carril de
   migraciones `pg`, esquema base del Inbox, pruebas de integración contra un PostgreSQL real.
5. **Slice 4 — Inbox central y API `/sync`.** Autenticación de estación, autorización con el catálogo
   único, idempotencia y ACK/rechazo/conflicto.
6. **Slice 5 — Ventas + Inventario** de punta a punta: venta local → evento → ingesta central →
   proyección consolidada. Requiere cerrar la ronda FID 968e0bc (R-08).
7. **Slices 6–9:** Caja/crédito/fidelidad/finanzas → compras/producción/logística → datos maestros →
   CRM/BI/WhatsApp.
8. **Slices 10–11:** instalador y despliegue; respaldos PG y pruebas de 5 sucursales.

Cada slice entrega código, migración, autorización, pruebas ejecutadas, manejo de errores, documentación y
rollback.

## Decisiones del usuario (resueltas el 2026-10-23)

1. PostgreSQL central en **Oracle Cloud Always Free (ARM64)**: ADR-001.
2. Autoridad central y local **como dice el TRD §9**: ADR-002.
3. **No replicar** el modelo heredado: ADR-003.

Ver `08_decisions_adr.md`.

## Gate de salida de la Fase 0

- [x] Inventario arquitectónico con rutas, estado y clasificación (01).
- [x] Dependencias de SQLite contadas, y semántica de conexión probada (02).
- [x] Esquema medido sobre una copia real (03).
- [x] Flujo entre módulos con evidencia (04).
- [x] Matriz de reutilización: **extender** casos de uso, outbox, `DatabaseSettings`, API, respaldo e
  instalador; **consolidar** los tres motores de sincronización; **crear** sólo el transporte HTTPS, la
  credencial de estación y el respaldo PG (05).
- [x] Riesgos con mitigación; **R-01 bloquea el Outbox** (06).

La implementación empieza por el **Slice 0**, que es independiente de las decisiones de arriba.
