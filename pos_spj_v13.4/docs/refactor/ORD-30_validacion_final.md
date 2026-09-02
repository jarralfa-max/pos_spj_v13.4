# ORD-30 — Validación final

Fecha: 2026-09-01. Alcance: master prompt ORD-30 ("Ejecutar: tests de dominio, tests de
aplicación, tests de integración, tests e2e, tests de seguridad, tests UI, tests PWA,
tests de arquitectura, bootstrap limpio, auditoría UUIDv7, auditoría Decimal, auditoría
[texto truncado en la captura original del prompt maestro — no recuperable de esta
sesión]").

**ORD-29 (eliminación de legacy) NO se ejecutó** — el usuario confirmó explícitamente
posponerlo: el nuevo stack `backend/domain|application/orders_delivery` está completo y
probado, pero NO está conectado a la UI de producción (`modulos/delivery.py` sigue siendo
la única pantalla que ven los usuarios reales, corriendo sobre `core/delivery/` legacy).
Eliminar el legacy ahora, tal como ORD-29 lo especifica literalmente, habría roto la
operación de entregas en producción sin ningún reemplazo sirviendo tráfico real. Ver
`docs/refactor/ORD-28_ui_ux.md` y la memoria persistente para el detalle de esta decisión.

## Resultados de la validación

### Tests (dominio + aplicación + integración + seguridad + arquitectura + UI + PWA)

Suite curada completa de Pedidos/Delivery + Logística móvil (Procurement, que este
pipeline también tocó vía la extracción de infraestructura compartida en ORD-25):

```
tests/unit/test_orders_delivery_*.py
tests/integration/test_orders_delivery_*.py
tests/unit/logistics/
tests/integration/logistics/
tests/architecture/test_orders_delivery_permissions_are_granular.py
```

**418/418 pasando.** Desglose acumulado por fase (ver cada `docs/refactor/ORD-N_*.md`
para el detalle):

| Fase | Qué prueba | Tests |
|------|-----------|-------|
| ORD-1..21 | Dominio + aplicación del "core delivery" (captura → pago → liquidación) | 309 |
| ORD-22 | Integración Ventas/Finanzas | +26 |
| ORD-23 | Notificaciones WhatsApp al cliente | +19 |
| ORD-24 | Dispatcher del outbox transaccional | +8 |
| ORD-25 | API + PWA de repartidor (incluye logística de Procurement re-verificada) | +18 (9 nuevos + 9 previos revalidados tras refactor compartido) |
| ORD-26 | Notificaciones internas + políticas | +13 |
| ORD-27 | Analytics (KPI/SLA/rendimiento de repartidores) | +9 |
| ORD-28 | 3 páginas reales de escritorio + 1 diálogo | +10 |
| Arquitectura (ORD-1) | Permisos granulares | 5 |

No se ejecutaron "tests e2e" como una categoría separada — cada fase construyó su propia
prueba de "pipeline real completo" (captura→confirmar→reservar→preparar→despachar→
entregar→cobrar→liquidar, y ahora también dispatch→notificar→analizar) contra SQLite real,
nunca mocks — esa disciplina, mantenida las 28 fases, es lo que este proyecto usa en vez
de una suite e2e separada.

### Bootstrap limpio

`python scripts/bootstrap_db.py --db <nueva>` desde una base de datos vacía: **migración
226 (esquema de Pedidos/Delivery) se ejecuta sin ningún error**, correctamente posicionada
después de Loyalty (225) y antes de las migraciones de seguimiento de Loyalty (227+). Los
3 errores que el bootstrap SÍ reporta (migraciones 024/029/080 — `venta_id`,
`movimientos_caja`, `cierres_caja`) son de migraciones legacy no relacionadas
(Ventas/Caja, anteriores a ORD-1), no de este bounded context.

### Auditoría UUIDv7

- Cero `AUTOINCREMENT`/`INTEGER PRIMARY KEY` en todo `orders_delivery_schema.py`.
- Cero `int(...)` aplicado a cualquier campo `_id`/`.id` en `backend/domain/orders_delivery/`
  o `backend/application/orders_delivery/`.
- Todo evento (`OrderEvents`/`DeliveryEvents`) valida `operation_id`/`entity_id`/
  `branch_id`/`user_id` como UUIDv7 canónico vía `validate_uuidv7()` — confirmado el bug
  real que esto mismo atrapó en ORD-21 (ver ese documento).

### Auditoría Decimal

- Cero `float(...)` en `backend/domain/orders_delivery/`, `backend/application/
  orders_delivery/` ni en los repositorios de infraestructura.
- Las únicas excepciones confirmadas, todas documentadas explícitamente en su propio
  código como decisiones deliberadas: `order_addresses.latitude/longitude` (SQL `REAL`,
  ORD-7 — coordenadas geográficas, no un valor de negocio), `DeliveryEvidence.latitude/
  longitude` (ORD-18, mismo motivo), y la conversión Decimal→float en
  `frontend/desktop/modules/orders_delivery/presenters/analytics_presenter.py` (ORD-28 —
  únicamente en la frontera de renderizado de gráficos, nunca en el query service que
  sigue siendo 100% Decimal).

### Auditoría de sintaxis

`ast.parse()` sobre las 4,698 archivos `.py` del repositorio (excluyendo `.venv`/`.git`/
`__pycache__`): **cero errores de sintaxis.**

## Estado final del pipeline ORD-0..30

| Fase | Estado |
|------|--------|
| ORD-0 (auditoría) | ✅ Completa |
| ORD-1 (seguridad) | ✅ Completa |
| ORD-2..21 (core delivery: dominio, esquema, captura, programación, direcciones/zonas, inventario, preparación, peso variable, aprobación, sustituciones, empaque, pickup, DeliveryJob, repartidores, rutas, despacho/entrega, fallas/reentregas, cobro, liquidación) | ✅ Completa |
| ORD-22 (Ventas/Finanzas) | ✅ Completa |
| ORD-23 (notificaciones WhatsApp cliente) | ✅ Completa |
| ORD-24 (outbox dispatcher) | ✅ Completa |
| ORD-25 (API + PWA repartidor) | ✅ Completa (backend real y probado; frontend construido, no verificado en navegador real) |
| ORD-26 (notificaciones internas + políticas) | ✅ Completa (política estática, no motor configurable en BD) |
| ORD-27 (analytics) | ✅ Completa (backend real; gráficos completados en ORD-28) |
| ORD-28 (UI/UX escritorio) | ⚠️ Parcial deliberada — 3 de 23 páginas reales + 1 diálogo; resto placeholder documentado |
| ORD-29 (eliminación de legacy) | ⏸️ Pospuesto — requiere decisión de producto sobre el cutover real antes de poder ejecutarse sin romper producción |
| ORD-30 (validación final) | ✅ Este documento |

## Pendiente para una futura sesión (si se retoma este trabajo)

1. **Decisión de cutover**: conectar `frontend/desktop/modules/orders_delivery/` a
   `main_window.py`/`menu_lateral.py` para que sirva tráfico real, como prerequisito real
   de ORD-29.
2. Las ~20 páginas de escritorio restantes (ORD-28).
3. Selección real de producto en "Nuevo pedido" (`ProductSearchBox` + `SearchProvider`).
4. Endpoint de ubicación GPS en la PWA de repartidor (ORD-25).
5. Verificación manual en navegador/dispositivo real del frontend de la PWA (ORD-25) y en
   PyQt5 real (no solo headless) de las páginas de escritorio (ORD-28).
6. Motor de políticas de notificación configurable por sucursal (ORD-26, si el negocio lo
   pide).
7. ORD-29 en sí, una vez resuelto el punto 1.
