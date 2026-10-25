# 08 — Decisiones de arquitectura (ADR)

Estado: **Aceptadas** el 2026-10-23. Las tres primeras las decidió el usuario; las demás se derivan de la
auditoría (00–07) y no contradicen ninguna instrucción.

## ADR-001 — El PostgreSQL central vive en Oracle Cloud Always Free (ARM64)

**Decisión.** Una VM Ampere A1 (ARM64) de la capa Always Free de Oracle, con Ubuntu LTS, aloja PostgreSQL
16 (paquete nativo de la distribución), la API FastAPI (`uvicorn`, administrada por `systemd`) y un proxy
TLS (Caddy, certificado automático). Todo cuesta $0 MXN/mes.

**Consecuencias.**

- **Dependencias ARM64:**
  - `fastapi`, `uvicorn`, `httpx` y `pydantic` tienen ruedas `aarch64`.
  - El conector será `psycopg` 3 (`psycopg[binary]`, que también publica ruedas `aarch64`).
  - PyQt5 **no** se instala en el servidor: el backend central no importa `frontend/`.
- **Estaciones POS:** siguen en Windows con SQLite. El servidor sólo recibe HTTPS; nunca expone el puerto
  5432 a Internet.
- **Riesgo de la capa gratuita.** Oracle puede recuperar instancias inactivas y la capacidad A1 no
  siempre está disponible al crearla.

  Mitigación:
  - respaldo lógico diario fuera del servidor (ADR-007);
  - script de aprovisionamiento reproducible para recrear la VM;
  - el POS sigue vendiendo sin el central (criterio 1 del prompt).
- **Desarrollo:** PostgreSQL para Windows en la estación del desarrollador y servicio PostgreSQL en CI.
  No se usa Docker como requisito.

## ADR-002 — Autoridad de datos según el TRD §9

**Decisión.**

- **El central es autoridad** sobre identidad de usuarios y roles, catálogo maestro, campañas, folios
  compartidos, límites financieros globales (crédito), cupones y vales de uso único, y cierre consolidado.
- **La estación es autoridad temporal** sobre su turno de caja y sus movimientos locales (ventas, cobros,
  movimientos de inventario de su almacén) dentro de cupos explícitos.

**Consecuencias.**

- Una venta local confirmada se marca «pendiente central» hasta recibir el ACK, pero conserva su folio
  local y su integridad.
- Los cupones y vales de uso único y el crédito global exigen al central o un cupo asignado de antemano a
  la estación (TRD §6). Sin cupo y sin red, la operación se bloquea con un mensaje claro.
- La matriz detallada de autoridad por agregado es un entregable de la Fase 1.

## ADR-003 — El modelo heredado no se replica

**Decisión.** `ventas`, `detalles_venta`, `payments` (heredado), `inventario_actual`,
`movimientos_inventario`, `inventory_stock`, `lotes` y `clientes` (heredado) **nunca** llegan al central.
Sólo se replica el modelo canónico (decimales en `TEXT` → `NUMERIC`).

**Consecuencias.**

- BI corporativo lee el ledger canónico.
- Las 32 columnas `REAL` en tablas canónicas (03) se corrigen antes de replicar esas tablas, o se declaran
  fuera de alcance si están muertas.

## ADR-004 — Un solo motor de replicación, derivado de CASH-19

**Decisión.** Se generaliza `backend/application/cash_register/offline_sync.py` (sobres, secuencia por
estación, ACK/rechazo/conflicto, reintento exponencial). Inventario (INV-22) y Mermas migran a él y sus
motores se retiran. Los outbox de contexto son la fuente; no hay captura de cambios de tabla.

## ADR-005 — Migraciones PostgreSQL con el motor actual, sin Alembic

**Decisión.** Se agrega a `migrations/engine.py` un carril `pg` (lista explícita, `run(conn)`, idempotente)
con su propio esquema base por contexto replicado.

**Justificación.** El motor actual ya es explícito, auditado y conocido por el equipo. Alembic añadiría una
segunda fuente de verdad sobre el esquema.

## ADR-006 — Transacción explícita en cada unidad de trabajo (precondición del Outbox)

**Decisión.** Cada UoW abre su transacción (`BEGIN`, o `SAVEPOINT` si ya hay una abierta) sin depender del
modo de la conexión. La conexión del escritorio activa `foreign_keys=ON`. Cierra R-01 y R-02.

## ADR-007 — Respaldos

**Decisión.**

- **SQLite:** `SQLiteBackupService` (ya existe).
- **PostgreSQL:** `pg_dump` en formato personalizado, cifrado, con copia fuera de la VM (almacenamiento
  de objetos Always Free u otro destino gratuito), restauración de prueba automatizada y RPO/RTO medidos.

La replicación hacia el central **no** sustituye a los respaldos.
