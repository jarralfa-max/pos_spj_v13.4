# ORD-1 — Seguridad (Pedidos/Delivery)

Fecha: 2026-08-28
Alcance: master prompt §62-65 (Permisos, Segregación de funciones, Autorización en caliente) + §68 (frontera de navegación del bounded context).
Precede a cualquier relocalización de dominio real (ORD-2+) — mismo orden que CASH-1/CRM-2/SALES-2/LOY-1.
Precondición: ORD-0 (`docs/refactor/orders_delivery_legacy_inventory.md`) — confirmó que
`core/security/permission_catalog.py` no tenía NINGÚN código `DELIVERY_*`/`ORDERS_*`/
`PEDIDOS_*`/`DRIVER_*` granular; el único control de acceso existente era el permiso
plano `DELIVERY.ver` que gatea el botón "🛵 Delivery" del menú lateral.

## Qué se construyó

- `backend/domain/orders_delivery/exceptions.py` — `OrdersDeliveryDomainError` + errores
  de seguridad (`OrdersDeliveryPermissionDeniedError`, `OrdersDeliveryConfigurationError`,
  `OrdersDeliverySegregationOfDutiesError`, `InvalidOrdersDeliveryAuditFieldError`).
- `backend/domain/orders_delivery/value_objects/authorization_grant.py` —
  `AuthorizationGrant`, con campos adicionales `quantity`/`weight`/`order_id`/
  `delivery_job_id` respecto al mirror de Loyalty, porque el master prompt §65 exige
  explícitamente esos campos de auditoría para este bounded context (ajustes de peso,
  reversos de entrega).
- `backend/domain/orders_delivery/value_objects/orders_delivery_audit_entry.py` —
  `OrdersDeliveryAuditEntry`.
- `backend/application/orders_delivery/permissions.py` — `OrdersDeliveryPermissions`,
  49 códigos granulares agrupados como en el master prompt §63: acceso, pedidos,
  preparación, aprobación del cliente, delivery/última milla, repartidores, cobro y
  liquidación, configuración.
- `backend/application/orders_delivery/{authorization,session_authorization,audit}.py`.

Mirrorea exactamente `backend/application/loyalty/{permissions,authorization,
session_authorization,audit}.py` (LOY-1): `PermissionChecker` Protocol,
`AllowAll.../DenyAll...ForTests`, `require()`/`has_permission()` fail-closed sin
checker, `authorize_exception()` con autorizador obligatoriamente distinto del
solicitante (`OrdersDeliverySegregationOfDutiesError`), y persistencia de auditoría
reutilizando el sink existente `core.services.auto_audit.audit_write` (sin tabla
paralela).

## Decisión de catálogo (aplica [[feedback_permissions_compras_standard]])

Se extendió la clave YA existente en `CANONICAL_MODULE_PERMISSIONS` (`DELIVERY`, ligada
al botón real del menú lateral "🛵 Delivery") en vez de crear una clave paralela
`ORDERS`/`PEDIDOS`/`ORDERS_DELIVERY`. Los 4 códigos planos originales
(`ver`/`crear`/`asignar`/`entregar`) se conservan por compatibilidad. Pedidos y Delivery
comparten esta única clave/entrada de navegación (master prompt §68: un solo sidebar
"PEDIDOS Y DELIVERY"), a diferencia de Fidelidad/Loyalty Cards que sí son dos claves
separadas — aquí el propio master prompt exige una sola. Test
`test_no_orders_or_pedidos_parallel_module_key_was_created` bloquea que alguien
reintroduzca una clave paralela en el futuro.

## Wiring real (no solo declarado)

`core/app_container.py` ahora construye `self.orders_delivery_authorization_policy` con
`OrdersDeliverySessionPermissionChecker(self.session)` — el mismo patrón de sesión viva
usado por `customer_authorization_policy`/`sales_authorization_policy`/
`loyalty_authorization_policy`. Verificado importando `AppContainer` y comprobando que
la construcción de la política y su `has_permission()` no lanzan excepción; el resto de
`AppContainer.__init__` (que corre después del bloque nuevo, sin depender de él) falla
más adelante por un gap preexistente y no relacionado del script `scripts/bootstrap_db.py`
contra una DB completamente nueva (tabla `configuraciones` ausente, cobertura 80% —
mismo tipo de gap de bootstrap ya documentado en memoria para `_born_clean_db.py`,
no introducido por este cambio).

**Explícitamente NO hecho, señalado no oculto**: ni `modulos/delivery.py` ni
`core/services/delivery_service.py` ni ningún caso de uso de `core/delivery/application/`
llaman todavía a esta política — se confirmó (grep) que `modulos/delivery.py` no tiene
ningún check de rol hardcodeado tipo `{"admin","gerente"}` que reemplazar (a diferencia
de `modulos/ventas.py` en SALES-2); su único campo relacionado, `self.rol`, se asigna
pero nunca se lee en todo el archivo. Tampoco existe ningún check de permiso/rol en
`core/delivery/application/action_policy.py` ni en el resto de `core/delivery/`. Por lo
tanto no hay una corrección "real y contenida" equivalente que aplicar en esta fase —
mismo caso que LOY-1. Hoy el módulo legacy sigue gateado únicamente por el permiso plano
de visibilidad (`DELIVERY.ver`) vía el menú lateral, sin distinción granular interna.
Las fases ORD-2+ (que relocalizarán `core/delivery/` a
`backend/domain|application/orders_delivery/` y construirán los casos de uso reales)
serán quienes efectivamente llamen `require()`/`authorize_exception()`. Ningún rol tiene
sembrados los códigos granulares nuevos (`_seed_system_roles` no fue tocado) — mismo
criterio ya establecido en SALES-2/COMPRAS/LOY-1: nunca auto-otorgar una acción granular
nueva, un admin debe concederla explícitamente vía Configuración → Seguridad → Permisos.

## Tests

23 tests nuevos, todos pasando:
- `tests/unit/test_orders_delivery_security.py` (18) — política, autorización en
  caliente, segregación de funciones, value objects de auditoría (incluye el caso propio
  de `weight` como Decimal obligatorio, ausente en el mirror de Loyalty).
- `tests/architecture/test_orders_delivery_permissions_are_granular.py` (5) —
  granularidad, prefijo de catálogo, sin duplicados, registro 1:1 en
  `permission_catalog.py`, sin clave paralela.

## Pendiente para fases futuras

- ORD-2/ORD-3 (relocalizar `core/delivery/` a `backend/domain|application/orders_delivery/`
  + resolver la triplicación de dueño de esquema, ver `orders_delivery_legacy_inventory.md`
  §3) serán el primer consumidor real de `OrdersDeliveryAuthorizationPolicy.require()`.
- Ningún rol tiene otorgados los nuevos permisos granulares todavía — verificar con el
  usuario/administrador antes de asumir que cualquier rol existente podrá operar los
  nuevos flujos sin configuración adicional.
- Los bloqueadores cruzados documentados en ORD-0 (identidad de cliente, `bot_pedidos.py`
  vs `whatsapp_service`, proyección directa a `ventas`) siguen abiertos y no fueron
  tocados en esta fase.
