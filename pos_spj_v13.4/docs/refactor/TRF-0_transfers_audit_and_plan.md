# TRF-0 — Auditoría de transferencias, tránsito y recepción interna

**Fecha de auditoría:** 2026-07-24  
**Alcance:** el árbol fuente actual, el esquema base y las migraciones activas.

## Resultado ejecutivo

El repositorio contiene **cuatro modelos de documento de transferencia** y dos
flujos de inventario activos. Ninguno puede declararse canónico todavía:

1. `repositories/transferencias.py` + `modulos/transferencias.py` opera
   `transfers` / `transfer_items` directamente.
2. `backend/domain/inventory/entities/transfer.py` + sus casos de uso opera
   `inventory_transfer` / `inventory_transfer_line`.
3. `transferencias` / `transferencia_detalle` sigue siendo creado por el schema
   base y por la migración 031.
4. `stock_transfers` / `stock_transfer_lines` fue introducido como destino de
   TRF-3, pero aún no está registrado por el bootstrap ni tiene repositorios,
   Use Cases, rutas o UI consumidores.

Por tanto, TRF-0 **no autoriza borrar ni migrar todavía**. Primero deben existir
tests de caracterización y una ruta canónica completa; después se aplicará el
gate de cero consumidores de `SPJ_REFACTOR_SKILL.md`.

## 1. Inventario de archivos y rutas

| Área | Archivo o ruta | Rol actual | Clasificación TRF |
|---|---|---|---|
| UI legacy | `modulos/transferencias.py` | tabs, diálogos, KPIs, sugerencias y recepción | REWRITE → DELETE |
| UI QR | `modulos/recepcion_qr_widget.py` | informa que Transferencias es dueño de la recepción, sin ejecutar el flujo | REUSE |
| UI wiring | `interfaz/main_window.py`, `core/ui/module_loader.py` | importa y registra `ModuloTransferencias` | MOVE → DELETE |
| Repo legacy | `repositories/transferencias.py` | lectura/escritura SQL, inventario, eventos y cancelación | DELETE |
| Query legacy | `backend/application/queries/transfer_query_service.py` | lectura para UI sobre `transfers` | REWRITE |
| Stats legacy | `backend/infrastructure/db/repositories/transfers_stats_repository.py` | KPIs sobre `transferencias` | DELETE |
| Dominio de Inventario | `backend/domain/inventory/entities/transfer.py` | agregado alterno de transferencia | MOVE / absorb into Transfers |
| Casos de Inventario | `backend/application/inventory/use_cases/transfer_use_cases.py` | crea, aprueba, despacha y recibe con ledger | MOVE / split |
| Repo de Inventario | `backend/infrastructure/db/repositories/inventory/transfer_repository.py` | persistencia de `inventory_transfer` | REWRITE |
| Puente de eventos | `backend/application/event_handlers/inventory/transfer_items_bridge.py` | publica movimientos desde `TRANSFER_ITEMS_PROCESS` | REWRITE |
| Sugerencias | `core/services/transfer_suggestion_engine.py` | DOS/CV, SQL, IDs enteros y `float` | REWRITE |
| Sugerencias alternas | `core/services/franchise_manager.py` | redistribución alternativa y SQL | REWRITE / consolidate |
| Nuevo destino | `backend/domain/transfers/`, `backend/application/transfers/` | dominio, eventos, puertos y permisos iniciales | REUSE / complete |
| Nuevo schema | `backend/infrastructure/db/schema/transfers_schema.py` | DDL target sin bootstrap | REUSE / wire |

## 2. Inventario de tablas

| Tabla | Creador actual | Consumidor principal | Cantidades | Estado / conclusión |
|---|---|---|---|---|
| `transferencias` | `m000_base_schema.py`, 031 | stats repository | `REAL` / legacy | DELETE at cutover |
| `transferencia_detalle` | `m000_base_schema.py`, 031 | sin ruta canónica | `REAL` / legacy | DELETE at cutover |
| `transferencias_inventario` | `m000_base_schema.py` | legacy inventory | legacy | DELETE at cutover |
| `transfers` | `m000_base_schema.py`, 023, 031 | legacy repository/UI/query | `REAL` | DELETE at cutover |
| `transfer_items` | `m000_base_schema.py`, 023, 031 | legacy repository/UI/query | `REAL` | DELETE at cutover |
| `inventory_transfer` | `inventory_schema.py`, 125 | inventory transfer repo/use cases | decimal `TEXT` | MOVE ownership to Transfers |
| `inventory_transfer_line` | `inventory_schema.py`, 125 | inventory transfer repo/use cases | decimal `TEXT` | MOVE ownership to Transfers |
| `transfer_suggestions` | 038 | legacy suggestions engine | `REAL`, integer-era references | REWRITE |
| `stock_transfers` | 135 / `transfers_schema.py` | no runtime consumers | decimal `TEXT` | canonical target |
| `stock_transfer_lines` | 135 / `transfers_schema.py` | no runtime consumers | decimal `TEXT` | canonical target |
| `transfer_shipments`, `transfer_receipts`, `transfer_receipt_lines`, `transfer_differences`, `transfer_outbox` | 135 | no runtime consumers | decimal `TEXT` | canonical target |

`traspasos_inventario` and `traspasos_pollo` are also present in the schema
history and must be included in the zero-consumer search before final deletion.

## 3. Estados y workflows encontrados

| Ruta | Estados | Hallazgo |
|---|---|---|
| `transfers` legacy | `DISPATCHED`, `RECEIVED`, `CANCELLED` | dos fases; no reserva, picking, tránsito separado o recepción acumulativa |
| `inventory_transfer` | `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `PICKING`, `READY_TO_DISPATCH`, `IN_TRANSIT`, `PARTIALLY_RECEIVED`, `RECEIVED`, `WITH_DIFFERENCES`, `CLOSED`, `REJECTED`, `CANCELLED` | más completo, pero aún vive en Inventario y no modela embarques/receipts |
| `stock_transfers` target | catálogo TRF de estados | debe incorporar reserva, parcial de picking/despacho, devoluciones y reversos en casos de uso |

## 4. Movimientos e inventario en tránsito

* La ruta legacy hace salida y entrada directa por `repositories/transferencias.py`;
  además usa `TRANSFER_ITEMS_PROCESS` de forma condicional según handlers.
* La ruta Inventory usa `MovementType.TRANSFER_DISPATCH` al despachar y
  `MovementType.TRANSFER_RECEIPT` al recibir, dentro de `InventoryUnitOfWork`.
  Es la regla válida a preservar: origen deja disponible en despacho y destino
  sólo gana disponible en recepción.
* Ninguna ruta actual implementa un agregado de `TransferShipment` ni una
  posición explícita de tránsito ligada a `shipment_id` en Transfers.
* Riesgo crítico: mantener el repo legacy y los Use Cases de Inventario deja dos
  rutas que pueden afectar stock.

## 5. Recepción y diferencias

* El repositorio legacy impide doble recepción, impide recibir más que enviado,
  registra receptor/fecha y calcula diferencias por producto; actualmente sólo
  admite una recepción final `DISPATCHED → RECEIVED`.
* El agregado de Inventario sí permite `PARTIALLY_RECEIVED`, pero no almacena
  documentos de recepción independientes, recepción ciega, QR de transferencia,
  evidencia, inspección de calidad ni resolución de diferencias.
* `RecepcionQRWidget` correctamente evita duplicar la recepción de transferencias
  y redirige al módulo de Transferencias; el QR canónico de compras pertenece a
  Procurement y no debe reutilizarse como ruta de inventario de transferencias.

## 6. Sugerencias de redistribución

`TransferSuggestionEngine` conserva lógica valiosa de velocidad, smoothing,
DOS y coeficiente de variación, pero usa SQL, IDs `int`, cantidades `float`,
defaults hardcodeados y es invocado desde el widget. `FranchiseManager` duplica
una sugerencia más simple. La fase TRF-16 debe convertir ambos en un único
`TransferSuggestionService` Decimal/UUID, alimentado por Query Services y
configuración; una sugerencia nunca debe mover stock ni crear una transferencia
aprobada automáticamente.

## 7. Eventos

| Evento/ruta | Situación | Acción |
|---|---|---|
| `TRASPASO_INICIADO`, `TRASPASO_CONFIRMADO`, `TRASPASO_CANCELADO` | publicados por UI/repo legacy y exportados por EventBus | DELETE |
| `TRANSFER_ITEMS_PROCESS` | puente condicional a movimientos | REWRITE as canonical post-commit handler |
| `INVENTORY_TRANSFER_*` | eventos del agregado que hoy vive en Inventario | MOVE/re-map to `TRANSFER_*` |
| `backend.domain.transfers.TransferEvents` | catálogo target | REUSE; conectar a outbox post-commit |

## 8. Permisos

| Fuente | Situación | Acción |
|---|---|---|
| `core/security/permission_catalog.py` | permiso general `TRANSFERENCIAS` (`ver`, `crear`, `recibir`, `cancelar`) | DELETE |
| `InventoryPermissions.TRANSFER_*` | permisos de transferencia bajo Inventario | MOVE/re-map |
| `TransferPermissions` | catálogo granular target `TRANSFERS_*` | REUSE; registrar y autorizar en backend |

## 9. Plan de ejecución controlado

1. **TRF-1 Seguridad:** registrar `TRANSFERS_*`, scopes por branch/warehouse,
   segregación, autorizaciones en caliente y auditoría; caracterizar permisos
   legacy antes de retirar el general.
2. **TRF-2 Dominio:** completar el agregado target con approvals parciales,
   allocations, picks, packages, shipments, custody, returns, resolutions and
   cold-chain policies; ampliar tests de transición.
3. **TRF-3 Esquema y persistencia:** registrar el schema target en bootstrap,
   crear repositorios focalizados y outbox; no ejecutar lecturas/escrituras duales.
4. **TRF-4–15 Workflow:** implementar requests through returns a través de
   Use Cases que dependan de los puertos de Inventario; cada mutación se prueba
   atómicamente e idempotente.
5. **TRF-16–21 Integración/UI:** mover sugerencias, crear Query Services y UI
   SPJ Design System, QR de transferencias, offline/outbox, alertas e impresión.
6. **TRF-22 Cutover:** buscar imports, instanciaciones, rutas, eventos,
   dynamic loader, feature flags y tests; con cero consumidores, eliminar las
   cuatro familias de tabla, UI/repo/eventos/permisos legacy y dejar allowlist
   vacía.
7. **TRF-23 Validación:** ejecutar domain/application/integration/e2e/security/
   architecture tests y bootstrap limpio antes de declarar `MIGRATED`.

## Tests de caracterización requeridos antes de cada corte

* despacho reduce disponibilidad de origen y registra tránsito;
* recepción parcial acumulativa, doble recepción y sobre-recepción;
* segregación despachador/receptor y permisos/scopes;
* cancelación antes/después de reserva y retorno/reverso tras despacho;
* idempotencia de request, dispatch, receipt, outbox y notificación;
* piezas + peso Decimal, lote, caducidad, temperatura y diferencias;
* sugerencias DOS/CV fuera de UI y QR sólo por la ruta de Transferencias;
* arquitectura: sin SQL/repos en UI, sin eventos legacy, sin fallback directo,
  sin tablas duplicadas y sin `float`/`REAL` crítico.
