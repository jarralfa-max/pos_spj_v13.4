# Slice 2 — Motor de replicación único (ADR-004)

Fecha: 2026-10-24. Migración **350**. Sin commit.

## Inventario real (corrige la auditoría)

La Fase 0 contó tres motores parciales. Al abrirlos aparecieron cuatro, y no todos cumplen el mismo papel:

| Motor | Papel | Uso en producción | Decisión |
|---|---|---|---|
| Caja CASH-19 (`cash_register/offline_sync.py`) | Envío estación → servidor desde `cash_outbox` | Pantalla de sincronización de Caja, **sin transporte** | **Consolidado**: Caja usa el motor único; mismas clases para la pantalla |
| Inventario INV-22 (`inventory/sync/outbox_dispatcher.py`, `transport.py`) | Envío desde `inventory_outbox` | Ninguno (código muerto, lo decía su propio código) | **Retirado**. El ingestor idempotente (lado receptor) se conserva hasta el Slice 4 |
| Mermas LOSS-22 (`losses/offline.py` + repositorio + almacén de evidencias) | Captura offline de borradores y su envío | Ninguno (sólo pruebas) | **Retirado**. Con la base local siempre disponible, la merma se registra directo; el registro normal ya maneja y exige evidencias |
| Transferencias (`transfers/offline_sync.py`) | **Lado receptor**: huecos de secuencia, huella y versión del agregado | Ninguno | **Se conserva**: es la base natural de la bandeja de entrada central (Slice 4) |

## Defecto vivo encontrado y corregido

El motor de CASH-19 tomaba todas las filas de `cash_outbox` de la sucursal y escribía su `status` en tres
casos: al reintentar (`FAILED`), en un conflicto (`FAILED`) y al aceptar o resolver (`DISPATCHED`). Esa
columna pertenece al despachador en proceso que lleva la Caja a Finanzas (CASH-26), que **sólo toma filas
`PENDING`**.

Como no hay servidor configurado, bastaba que alguien con `CAJA.sincronizacion.gestionar` pulsara
«Sincronizar». Esto pasaba:

1. el transporte fallaba;
2. los movimientos de caja quedaban en `FAILED`;
3. **nunca se asentaban en Finanzas**.

En la copia de la base real los outbox están vacíos, así que no llegó a dañar datos.

**Corrección:**

- El motor único lleva su propio estado y nunca escribe el `status` de un outbox de contexto. Una guarda de
  arquitectura (`test_sync_never_writes_the_finance_outbox`) lo impide.
- La migración 350 repara lo que haya dañado, tocando sólo filas cuyo `last_error` es del motor viejo:
  - sin `dispatched_at`: vuelven a `PENDING`, para que Finanzas las reciba;
  - con `dispatched_at`: vuelven a `DISPATCHED`.

## Qué se construyó

| Pieza | Archivo |
|---|---|
| Esquema: `replication_stations`, `replication_envelopes` | `migrations/standalone/350_replication_engine.py` (DDL propio de la migración) |
| Fuentes: 26 outbox de contexto con un lector genérico | `backend/infrastructure/sync/replication_sources.py` |
| Repositorio + UoW (hereda la frontera del Slice 0) | `backend/infrastructure/db/repositories/replication/` |
| Motor | `backend/application/sync/replication_outbox.py` |
| Caja sobre el motor | `backend/application/cash_register/offline_sync.py` (fachada; la pantalla no cambió) |

### Cómo trabaja

1. **Preparar.** Cada hecho nuevo de un outbox recibe su sobre (el contrato del Slice 1), con la secuencia
   siguiente de la estación y la versión siguiente de su agregado.
   - Las tablas difieren (`event_name`/`event_type`, `payload_json`/`payload`, con o sin `event_id`).
     `normalize()` las lleva a la forma canónica; lo que falta se deriva de forma **determinista** del id
     de la fila, así que un reintento produce el mismo sobre.
   - Un hecho que no cumple el contrato (un `float`, por ejemplo) queda **MUERTO con su motivo**: visible,
     sin trabar a los demás.
   - Si el mismo `event_id` aparece en dos outbox, se envía una sola vez.
2. **Recuperar.** Un sobre EN VUELO con más de 5 minutos (un cierre o una caída a media entrega) vuelve a
   reintento. La entrega es «al menos una vez» y el servidor deduplica por `event_id`.
3. **Enviar** un lote (máximo 500) en orden de secuencia, **fuera** de la transacción local: la red nunca
   retiene un bloqueo de la base.
4. **Aplicar acuses:**
   - `ACCEPTED` y `DUPLICATE` → `SYNCED`;
   - `CONFLICT` → `CONFLICT`, que bloquea **sólo a su agregado**. CASH-19 bloqueaba la estación entera:
     un conflicto en un turno detenía todas las ventas;
   - `REJECTED` → `DEAD`;
   - sin acuse, transporte caído o `RETRY` → reintento con espera exponencial con *full jitter* (de 1 s a
     15 min), para que cinco sucursales que vuelven a la vez no golpeen al servidor juntas;
   - 25 intentos → `DEAD`.
5. **Reencolar** (`requeue`) un `CONFLICT` o un `DEAD` reenvía **el mismo sobre**. CASH-19 le subía la
   versión, pero la versión forma parte de la huella: el servidor habría visto el mismo `event_id` con
   otro contenido.

### Lo que la pantalla de Caja conserva

- Mismas clases y permisos (`CAJA.sincronizacion.ver/gestionar`) y alcance por sucursal.
- Resolución de conflictos con motivo obligatorio y evento `CASH_SYNC_CONFLICT_RESOLVED`.
- El «dispositivo» de Caja es la estación de replicación. El ciclo envía todos los hechos de la estación;
  las vistas de Caja muestran los de Caja, y la lista de conflictos incluye también los envíos MUERTOS,
  porque ambos requieren una decisión.

## Evidencia

- `tests/integration/sync/test_replication_outbox.py`, 15 pasan, con outbox **reales** de Caja e
  Inventario:
  - secuencia y versión por agregado;
  - el sobre preparado cumple el contrato;
  - **el outbox de Caja queda `PENDING`**;
  - aceptado y duplicado;
  - transporte caído con espera aleatoria;
  - conflicto que bloquea sólo su agregado;
  - rechazado → muerto, sin acuse → reintento, 25 intentos → muerto y reencolable;
  - recuperación tras el plazo de 5 minutos;
  - hecho inválido visible sin trabar a los demás;
  - mismo hecho en dos outbox;
  - estación fuera de línea;
  - dinero exacto;
  - migración 350 (traslada estaciones y repara filas).
- `tests/integration/cash_register/test_cash_offline_sync.py`, reescrita al contrato nuevo: 7 pasan.
  - Las pruebas anteriores **exigían** que `cash_outbox` quedara `DISPATCHED`, el comportamiento defectuoso.
  - Ahora cubren también el alcance por sucursal, el motivo obligatorio, el permiso de gestión y el rastro
    de auditoría.
- La guarda de arquitectura de Caja exige que nada de la sincronización escriba `cash_outbox`.
- Caja, motor, contrato e Inventario juntos: 385 pruebas pasan.
- Copia de la base real: la 350 es idempotente y se puede correr un ciclo completo sin servidor;
  `integrity_check` sale ok, con 0 violaciones de llaves foráneas.

## Código retirado

- `backend/application/inventory/sync/outbox_dispatcher.py` y `transport.py`, con 6 pruebas del despachador.
- `backend/application/losses/offline.py`, `backend/infrastructure/persistence/loss_offline_repository.py` y
  `loss_evidence_store.py`, con sus 3 archivos de prueba.
- `CashSyncRepository` y `uow.sync` de Caja, más `tests/unit/cash_register/test_cash_offline_sync.py`
  (`retry_at`). La espera ahora la prueba `test_retry_policy_is_bounded_and_spread`.

Las tablas `cash_sync_*`, `loss_offline_*` y `loss_sync_outbox`, y las de INV-22, **se conservan**
(expandir/migrar/contraer): ya nadie escribe en ellas. Se retiran en una migración posterior, cuando una
versión publicada haya corrido la 350.

## Pendiente

- **Transporte HTTPS y servidor** (Slices 3–4). Hasta entonces `MissingReplicationTransport` deja todo en
  cola local, sin perder nada.
- **Ciclo en segundo plano.** Hoy sólo se ejecuta desde «Sincronizar» en Caja. El trabajador periódico del
  shell se conecta cuando exista transporte, para no producir reintentos sin destino.
- **Pantalla corporativa de sincronización** (todas las fuentes), con reencolado protegido por permiso.
  Hoy sólo Caja ofrece resolución.
- **Tipos de agregado finos por evento.** Cada fuente usa un agregado por omisión (`cash_register.cash`,
  `inventory.stock`…); los Slices 5–9 los afinan por contexto.
