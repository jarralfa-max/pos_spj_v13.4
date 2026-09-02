# ORD-25 — PWA de repartidor

Fecha: 2026-09-01. Alcance: master prompt ORD-25 ("1. API. 2. Offline. 3. Evidencia.
4. Cobro. 5. Sync. 6. Tests."). Reemplaza el prototipo legacy
`integrations/delivery_pwa/pwa_server.py` (http.server hecho a mano, HTML embebido como
strings de Python, tokens en un diccionario en memoria que se perdían al reiniciar el
proceso) — **no se eliminó** ese archivo; sigue siendo la ruta prototípica intacta hasta
que ORD-29 (eliminación de legacy) confirme cero consumidores.

## Hallazgo inicial que cambió el diseño

Antes de escribir código nuevo, una búsqueda de infraestructura de sesión existente
encontró `backend/api/` — un "FastAPI application skeleton for future SPJ API
entrypoints" YA construido (con su propio router+esquema para logística móvil de
Procurement, `mobile_logistics.py`), incluyendo `backend/api/mobile_session.py`:
`MobileSessionTokenService` (tokens HMAC-firmados de corta vida, sin fila en BD) +
`MobileIdentity` + protocolo `CredentialVerifier`. Esto invalidó mi primer intento (una
tabla `driver_pwa_tokens` con hash SHA-256 propia) — se descartó por completo antes de
tocar tests, y ORD-25 se construyó reusando esta infraestructura compartida en vez de
duplicarla. Ninguna implementación REAL de `CredentialVerifier`/`OriginPurchaseWorkflow`
existía todavía en ningún lado del repo (solo protocolos + dobles de prueba) — esta fase
entrega la PRIMERA implementación real de ese patrón para cualquier router móvil, no solo
para Pedidos/Delivery.

## Qué se construyó

- **API** (`backend/api/routers/driver_logistics.py` +
  `backend/api/schemas/driver_logistics.py`): login vía el MISMO
  `POST /api/mobile/session` que ya usa Procurement (una sesión móvil no es un caso
  especial por repartidor); `GET /delivery/mobile/jobs`, `GET /delivery/mobile/
  assignments/pending`, `POST .../accept`, `.../reject`, `.../dispatch`, `.../depart`,
  `.../arrive`, `.../attempts` (evidencia), `.../cash-collections/{id}/record` (cobro).
  Cada mutación exige `Idempotency-Key` (UUIDv7) — SIN `If-Match`: a diferencia de los
  agregados de embarque/contenedor de Procurement, `DeliveryJob`/`CustomerOrder` no
  tienen columna de versión para control de concurrencia optimista, así que forzar un
  `If-Match` habría sido una ficción de API. `OrdersDeliveryDriverWorkflow`
  (`backend/application/orders_delivery/integrations/driver_pwa_workflow.py`) no toca SQL
  directo — delega TODO a los casos de uso reales ya construidos en ORD-15..20
  (`AcceptAssignmentUseCase`/`DispatchDeliveryJobUseCase`/`RecordDeliveryAttemptUseCase`/
  `RecordCashCollectionUseCase`, etc.).
- **Permisos reales, no simulados**: los permisos otorgados al repartidor viajan dentro
  de su `MobileIdentity.permissions` firmada (leída al login desde las mismas tablas RBAC
  `usuarios_roles`/`roles` que usa el escritorio) — `_IdentityPermissionChecker` los
  adapta al mismo protocolo `PermissionChecker` que cada caso de uso de Pedidos/Delivery
  ya exige, así que el backend revalida exactamente igual que la UI de escritorio, nunca
  confía en el cliente PWA.
- **Evidencia**: `POST .../attempts` expone `RecordDeliveryAttemptUseCase` completo
  (destinatario, referencia de firma/foto, PIN, lat/lon, notas, motivo de falla) — el
  modelo de dominio (`DeliveryEvidence`, ORD-18) ya existía; esta fase es la primera que
  lo expone a un cliente real.
- **Cobro**: `POST .../cash-collections/{id}/record` expone `RecordCashCollectionUseCase`
  (ORD-20) directamente.
- **Sync/Offline**: `frontend/web/delivery/` (nuevo) — PWA estática (HTML/CSS/JS +
  manifest + service worker), misma arquitectura que la PWA hermana de Procurement
  (`frontend/web/logistics/`): cola de comandos en IndexedDB (`store.js`), motor de
  sincronización con reintento (`sync.js`), generación de `operationId` UUIDv7 en el
  cliente (`uuidv7.js`, copiado literal — utilidad pura sin dependencias). Simplificado
  respecto al hermano: sin seguimiento de versión de agregado ni estado `CONFLICT` (no
  aplica, ver arriba sobre `If-Match`).

## Gaps encontrados en código YA CONSTRUIDO (no bugs nuevos de esta fase, pero surgieron
al construir el primer consumidor real)

- `DeliveryJobRepository`/`DeliveryAssignmentRepository` no tenían forma de consultar
  "mis pedidos"/"mis asignaciones pendientes" por `driver_id` — todo consumidor anterior
  consultaba por sucursal o por job. Se agregaron `list_for_driver()`/
  `list_pending_for_driver()`.
- **Bug real, dormido, en `backend/api/mobile_session.py`**: `mobile_identity()` (la
  dependencia FastAPI compartida pensada para cualquier router móvil) tenía
  `credentials: HTTPAuthorizationCredentials | None = None` en vez de
  `= Depends(bearer)` — FastAPI nunca habría extraído el header `Authorization` para
  ella. Nadie lo notó porque `routers/mobile_logistics.py` la esquivó definiendo su
  propia copia local, correctamente cableada, en vez de usar la compartida. Corregido; se
  extrajeron también `mutation_headers`/`command_payload` (antes duplicados solo en
  `mobile_logistics.py`) al módulo compartido, y `mobile_logistics.py` ahora los importa
  en vez de mantener su propia copia — verificado sin regresión (16/16 tests de logística
  de Procurement siguen pasando después del refactor).

## Decisiones

- **Reusar el login/sesión compartido, no crear uno propio para repartidores** — un
  repartidor es un `usuarios` normal con un `DriverOperationalProfile` (§33: identidad
  vive en RRHH/Usuarios, sin tabla de personas paralela), no una cuenta especial.
- **"Dispatch" vs "Depart" son dos pasos separados, no uno** — el propio modelo de
  dominio (`DeliveryLifecyclePolicy`, ORD-15) ya distingue `DISPATCHED` de `IN_TRANSIT`;
  la API expone ambos pasos en vez de colapsarlos, aunque en la práctica un repartidor
  pequeño probablemente los presione seguidos.
- **Sin endpoint de ubicación GPS en esta fase** — el prototipo legacy tenía un ping de
  ubicación contra una tabla `driver_locations` con clave entera legacy; construir su
  reemplazo real (o decidir reusar esa tabla con la nueva identidad UUIDv7) se deja
  pendiente, no silenciosamente resuelto.

## Honestidad sobre lo NO verificado

El frontend estático (`frontend/web/delivery/*.js/html/css`) se escribió con cuidado y
sigue la MISMA arquitectura ya probada de `frontend/web/logistics/`, pero **no se abrió
en un navegador real** — esta sesión no tiene esa capacidad. Lo que SÍ se verificó
automatizado: el shell HTML se sirve correctamente vía `TestClient` (`GET
/mobile/delivery/` devuelve 200 con el contenido esperado) y los módulos `.js` son JSON/
sintaxis válida por inspección. La lógica de UI en `app.js` (render de tarjetas,
flujo de login, cola offline) no tiene test automatizado — está fuera del alcance de lo
que un backend de pruebas puede verificar honestamente.

## Tests

9 tests nuevos de integración (`tests/integration/logistics/test_driver_pwa_api.py`):
autenticación requerida, listar asignaciones/pedidos, aceptar/rechazar asignación,
404 en asignación inexistente, validación UUIDv7 del `Idempotency-Key`, pipeline completo
despachar→salir a ruta→llegar→registrar entrega, registro de cobro, y que el shell de la
PWA se sirve. Suite combinada `orders_delivery` + `logistics` (Procurement + Pedidos):
**381/381 pasando**.

## Pendiente

- Endpoint de ubicación GPS (ver arriba).
- Verificación manual en navegador/dispositivo real del frontend.
- ORD-26 (Notificaciones: Customer/Internal/WhatsApp/Policies — extiende ORD-23 con
  notificaciones internas/staff y un motor de políticas configurable, mismo espíritu que
  CASH-20 ya estableció para Caja).
