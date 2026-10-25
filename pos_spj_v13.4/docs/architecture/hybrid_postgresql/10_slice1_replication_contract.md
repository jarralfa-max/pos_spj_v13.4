# Slice 1 — Contrato de replicación (§6.1, ADR-004)

Fecha: 2026-10-24. Sin commit.

## Qué existía

| Pieza | Qué tiene | Qué le faltaba para cruzar la red |
|---|---|---|
| `DomainEvent` (`backend/shared/events/event_contracts.py`) | Evento de dominio dentro del proceso | Estación, secuencia, versión de esquema, huella, reglas de serialización |
| Constructores por contexto (`cash_event_payload`, `commercial_instrument_event_payload`…) | Lo que cada contexto guarda en su outbox: `event_id`, `event_name`, `operation_id`, `entity_id`, `branch_id`, `user_id`, `timestamp`, `payload` | Ídem |
| `SyncEnvelope` de CASH-19 (`cash_register/offline_sync.py`) | 7 campos | Sucursal, estación, actor, fecha, correlación y causa, versión de esquema, tipo de agregado, huella |

Ninguno fija cómo viajan el dinero y las fechas, ni qué pasa si llega dos veces el mismo `event_id` con
contenido distinto.

## Qué se agregó

`backend/shared/sync/replication_envelope.py`. Vive en `shared` porque lo usan el escritorio y la API
central.

- **`ReplicationEnvelope`**: los campos del §6.1 (`event_id`, `operation_id`, `event_type`, `schema_version`,
  `aggregate_type`, `aggregate_id`, `aggregate_version`, `branch_id`, `workstation_id`, `sequence_no`,
  `actor_id`, `occurred_at`, `correlation_id`, `causation_id`, `payload`, `authorization`) más
  `envelope_version`.
- **Forma canónica** (`canonical_json`): claves ordenadas y sin espacios.
  - `Decimal` viaja como texto exacto y conserva la escala.
  - Los instantes deben tener zona horaria y se normalizan a UTC.
  - Un `float` se rechaza al construir el sobre **y** al leerlo; la lectura usa `parse_float` para eso.
- **`content_hash`**: SHA-256 de lo que el hecho *es*. Excluye secuencia, estación y correlación, que
  cambian al reenviar. Si el mismo `event_id` llega con otra huella, el servidor responde `CONFLICT` /
  `EVENT_ID_REUSED` y no sobrescribe. Un sobre alterado en el camino se detecta al leerlo
  (`CONTENT_HASH_MISMATCH`).
- **Validaciones con códigos estables**, para que el servidor responda sin ambigüedad:
  - identificadores UUIDv7 canónicos;
  - `event_type` en MAYÚSCULAS;
  - `aggregate_type` como `<contexto>.<agregado>`;
  - ordinales con mínimos;
  - payload de 256 KiB como máximo;
  - versión de sobre conocida.
- **`envelope_from_outbox_event`**: envuelve tal cual el evento que un contexto ya guardó en su outbox. No
  se toca ningún constructor de eventos existente.
- **`ReplicationAck` / `ReplicationOutcome`**: `ACCEPTED`, `DUPLICATE` (la misma huella, ya aplicado),
  `CONFLICT`, `REJECTED` (permanente, a revisión) y `RETRY` (transitorio). Sólo `ACCEPTED` y `DUPLICATE`
  liberan el sobre en la estación. Toda falla exige `error_code`.

`authorization` es una **referencia**, por ejemplo el permiso usado o el autorizador de una excepción. El
servidor vuelve a autenticar la estación y a autorizar al actor con el catálogo central; el sobre nunca
concede nada.

## Lo que este slice NO hace (a propósito)

- No reemplaza todavía el `SyncEnvelope` de CASH-19. Eso ocurre en el **Slice 2**, cuando su motor se
  generalice a `ReplicationOutbox` y lo usen Inventario (INV-22) y Mermas. Hasta entonces conviven dos
  sobres; el de siete campos queda como interno de Caja.
- No hay transporte ni servidor: son los Slices 2–4.

## Evidencia

- `tests/unit/shared/test_replication_envelope.py`, 28 pasan:
  - ida y vuelta exacta y determinista;
  - Decimal con escala;
  - UTC;
  - `float` rechazado al construir y al leer;
  - NaN, fechas sin zona, claves no textuales y tipos no serializables;
  - tope de tamaño;
  - diez violaciones de contrato con su código;
  - colisión `event_id`/`operation_id`;
  - huella que ignora el transporte pero no el hecho;
  - detección de alteración;
  - sobres ilegibles;
  - envoltura de un evento **real** de Caja (`cash_event_payload`);
  - acuses.
- Guardas de arquitectura relacionadas: sin fallas nuevas. Las 4 que fallan ya estaban entre las 23 previas.

## Siguiente

**Slice 2:** motor de replicación único. Se generaliza CASH-19 a un `ReplicationOutbox` que toma de los
outbox de contexto; los sobres se escriben en la misma transacción que el hecho (Slice 0 lo garantiza). Lo
completan secuencia por estación, reintento con *backoff* y *jitter*, estados, *dead-letter* y la migración
de INV-22 y Mermas, con el retiro de sus motores.
