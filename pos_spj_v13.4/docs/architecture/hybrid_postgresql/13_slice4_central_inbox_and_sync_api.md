# Slice 4 — Bandeja de entrada central y API de sincronización (§6.3, §8, §9)

Fecha: 2026-10-25. Migración central **p002**.

Con este slice el recorrido completo existe. El hecho se registra en la caja (SQLite) y el motor de
replicación (Slice 2) lo envía por HTTPS a la API central. El servidor autentica la estación, aplica las
reglas de ingesta y deja el hecho en PostgreSQL.

## Qué se construyó

| Pieza | Archivo |
|---|---|
| Credenciales de estación | `backend/application/sync/station_credentials.py` |
| Alta, suspensión y baja de estaciones | `backend/application/sync/station_admin.py` + `scripts/central_stations.py` |
| Ingesta central (puerto + reglas) | `backend/application/sync/central_ingestion.py` |
| Libro central en PostgreSQL | `backend/infrastructure/central/sync_inbox_repository.py` |
| API `POST /api/v1/sync/events` | `backend/api/routers/sync.py` |
| App del servidor central | `backend/api/central_app.py` (sólo salud y sincronización) |
| Transporte HTTPS de la estación | `backend/infrastructure/sync/http_transport.py` |
| Cabeza de agregado por estación | `migrations/pg/p002_aggregate_head_station.py` |

**Credenciales de estación:** un secreto aleatorio de 256 bits por estación. Se entrega una vez y en el
servidor sólo se guarda su SHA-256.

**App del servidor central:** es distinta de la API local de la estación, que atiende el teléfono de
Logística y las PWAs. El servidor central sólo expone salud y sincronización.

## Reglas de la ingesta (por sobre, en su propia transacción anidada)

| Situación | Respuesta | Qué queda en el servidor |
|---|---|---|
| Contrato inválido, versión desconocida o huella alterada | REJECTED + código | Nada |
| El sobre es de otra estación o de otra sucursal | REJECTED `STATION_MISMATCH` / `BRANCH_SCOPE` | Nada |
| Hecho nuevo | ACCEPTED | Hecho APPLIED; avanza la cabeza del agregado |
| Mismo `event_id`, misma huella (reenvío o respuesta perdida) | DUPLICATE (la estación lo da por entregado) | Sin cambios |
| Mismo `event_id`, otra huella | CONFLICT `EVENT_ID_REUSED` | Registro en `sync_conflicts`; el original intacto |
| Secuencia de la estación ya usada por otro hecho | CONFLICT `SEQUENCE_REUSED` | Nada (p. ej. una caja restaurada de un respaldo viejo) |
| La misma estación manda una versión ≤ a la última que escribió de ese agregado | CONFLICT `AGGREGATE_VERSION_REGRESSION` | Hecho en CONFLICT + `sync_conflicts` |
| Error de almacenamiento | RETRY | Sólo ese sobre se revierte |
| Dos entregas simultáneas del mismo hecho | Una ACCEPTED, la otra DUPLICATE | Un solo renglón (lo garantiza la PK) |

Las versiones de **otra** estación sobre el mismo agregado no son conflicto. Cada estación lleva su propia
cuenta (Slice 2); las reglas de negocio entre estaciones (por ejemplo, existencia negativa consolidada) son
de cada contexto en los Slices 5–9.

## Seguridad (§9)

**Autenticación por estación:**

- Encabezados `X-SPJ-Station-Id` + `Authorization: Bearer`.
- El 401 no dice si falló el id o el secreto.
- Una estación suspendida o dada de baja recibe 403. La baja es definitiva, para una estación perdida o
  reemplazada.

**Aislamiento:** una estación sólo escribe en su sucursal y con su propia identidad, aunque esté
comprometida.

**Límites:**

- cuerpo ≤ 8 MiB;
- ≤ 500 sobres por solicitud;
- tope de solicitudes por estación por minuto (429 con `Retry-After`).

**Trazabilidad:** `X-Request-ID` se recibe o se genera, se devuelve y queda en el log.

**Lado de la estación:**

- El transporte exige HTTPS con verificación de certificado; HTTP sólo contra `localhost` y de forma
  explícita.
- El secreto viaja únicamente en el encabezado, y ni la respuesta ni el log lo repiten.

**Sin credenciales privilegiadas en el cliente:** las cajas hablan con la API, nunca con PostgreSQL.

### Autorización del actor (pendiente declarado)

Hoy el límite es la estación: autenticada, activa y acotada a su sucursal. El sobre ya fue autorizado
localmente por el caso de uso de la caja, con el catálogo de permisos.

Revalidar el permiso del **usuario** en el servidor exige que usuarios y permisos estén replicados al
central (Slice 7, datos maestros). El puerto `ActorAuthorizer` ya existe; el `StationScopedAuthorizer` por
omisión se reemplaza en ese slice.

## Consolidación (sin motores duplicados)

| Motor | Destino |
|---|---|
| `transfers/offline_sync.py` (receptor: huecos, huella, versión) | **Retirado.** Lo hace la ingesta central para todos los contextos. La política de dominio `OfflineTransferPolicy` se conserva, con su prueba |
| `inventory/sync/event_ingestor.py` + repositorios de despacho de INV-22 | **Retirados.** La idempotencia por `event_id` la da `sync_inbox` |

Con esto, de los cuatro motores parciales encontrados en el Slice 2 queda **un solo motor de envío** en la
estación y **una sola ingesta** en el servidor.

## Evidencia

**Aquí (sin PostgreSQL):**

- `tests/unit/central_sync/test_central_ingestion.py`, 14 pasan, con el libro en memoria (simulación que
  respeta el contrato):
  - credenciales;
  - autenticación genérica;
  - suspensión y baja;
  - aceptado y duplicado;
  - conflicto sin sobrescribir;
  - secuencia reutilizada;
  - regresión de versión y versiones independientes entre estaciones;
  - alcance;
  - sobres alterados o ilegibles;
  - error de almacenamiento que revierte sólo un sobre;
  - tope de lote;
  - perdedor de una carrera.
- `tests/integration/central_sync/test_sync_api_end_to_end.py`, 9 pasan:
  - caja (SQLite + motor) → HTTPS → API → ingesta;
  - respuesta perdida tras confirmar → DUPLICATE;
  - secreto equivocado → todo en cola;
  - 401/403, 413, 400 y 429;
  - `X-Request-ID`;
  - servidor sin configurar → 503;
  - HTTPS obligatorio;
  - el secreto nunca vuelve en la respuesta.

**En el CI (`central-postgres`, PostgreSQL 16 real):** `tests/integration/central_pg/test_central_ingestion_pg.py`
prueba:

- aceptado, duplicado y secuencia contigua;
- conflictos registrados sin sobrescribir;
- alcance por sucursal;
- **dos entregas concurrentes del mismo hecho → una ACCEPTED y una DUPLICATE, un solo renglón**;
- caja SQLite → API real → PostgreSQL.

**Resultado en el CI:** el trabajo `central-postgres` de la ejecución 40201737153 (commit `719f71a5`,
2026-10-25) pasó **en verde** contra PostgreSQL 16, incluida la carrera de dos entregas simultáneas.

**Defecto encontrado al escribir la prueba concurrente:** si dos entregas del mismo hecho llegaban a la
vez, la que perdía la carrera respondía ACCEPTED, porque el servicio ignoraba que su inserción no había
ocurrido. Ahora vuelve a comparar la huella y responde DUPLICATE o CONFLICT.

## Pendiente

- **Configuración de la estación.** Falta el endpoint del servidor y el secreto en el almacén de secretos
  de la caja, capturados en el instalador. Falta también el ciclo periódico del motor en el shell. Se
  conectan en el Slice 10 (instalador), cuando exista el servidor. Hasta entonces la caja usa
  `MissingReplicationTransport` y todo queda en cola local.
- **Pantalla corporativa de conflictos** (`sync_conflicts`) con resolución autorizada.
- **Proyecciones por contexto** sobre el libro central (ventas, inventario, caja…): Slices 5–9.
- **Rate limit compartido** entre varias réplicas de la API: hoy es por proceso, suficiente para una sola
  VM.
