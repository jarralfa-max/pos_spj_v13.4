# SDLC-PRICE-002 — Lista de precios por cliente: sin caso de uso ni UI, varias listas posibles y elección arbitraria

- **Prioridad:** P1
- **Nivel de riesgo:** T1 (si el diseño confirma migración de `customer_price_list`, esa parte se trata como T0)
- **Origen:** `inputs/correcciones.md` C-08 (oleada 4); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P1 — Asignación de precios especiales por cliente ambigua»
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PRICE-001, SDLC-ARQ-PERM-005

## Problema
No hay forma soportada de asignar una lista de precios a un cliente: el repositorio tiene un `INSERT OR IGNORE` que nadie llama. La tabla admite varias listas por cliente y no guarda sucursal, canal ni vigencia; al resolver el precio se toma una lista activa con `LIMIT 1` sin orden, así que con dos listas el precio cobrado depende del orden físico de las filas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `backend/infrastructure/db/repositories/pricing/pricing_repository.py:238-241` — `assign_customer_list`: `INSERT OR IGNORE INTO customer_price_list`; sin llamadores en `backend/` ni `frontend/` (grep `assign_customer_list(` = solo la definición).
- `backend/infrastructure/db/repositories/pricing/pricing_repository.py:243-247` — `customer_list_id`: `... WHERE cpl.customer_id=? AND pl.status='ACTIVE' LIMIT 1` sin `ORDER BY`.
- `backend/infrastructure/db/schema/pricing_schema.py:76-82` — `customer_price_list(customer_id, price_list_id, assigned_at, PRIMARY KEY(customer_id, price_list_id))`: sin sucursal, canal, vigencia ni autor.
- `backend/application/pricing/permissions.py:51` — `CUSTOMER_LIST_ASSIGN = "PRECIOS.lista.cliente.asignar"` existe en el catálogo y nadie lo exige (grep sin otros usos).
- Única escritura real: el backfill legacy `migrations/standalone/150_pricing_backfill_from_legacy.py:265`.

## Impacto
Clientes con precio negociado pueden recibir otro precio sin aviso; no hay rastro de quién asignó qué.

## Objetivo
- Una asignación vigente por cliente/sucursal/canal, con alta, reemplazo y baja bajo `PRECIOS.lista.cliente.asignar`, fechas y auditoría.
- Una sola regla de prioridad documentada y probada (lista de cliente vs volumen vs descuento global).

## Alcance
- **Incluye:** caso de uso, UI (desde el expediente del cliente o desde Precios, según Design), esquema, regla de prioridad.
- **No incluye:** revisión por línea (SDLC-PRICE-001).

## Restricciones
CLAUDE.md reglas 1-3 y 13; `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO; permisos con `require()` y códigos `MODULO.accion` (memoria «Permissions: Compras standard»); sin pantalla duplicada en Configuración; migraciones probadas sobre copia de la BD; presupuesto $0; Windows. Nivel T1 (T0 para la migración).

## Trabajo previo relacionado
SDLC-ARQ-PERM-005 (permisos con dimensión de recurso/condición); memoria «Proveedores y Precios» (otorgable ≠ otorgado: sembrar el permiso a los roles reales).

## Preguntas abiertas
- ¿El precio por volumen reemplaza o complementa el precio negociado del cliente? complementa· bloquea `/sdlc-design SDLC-PRICE-002`
- ¿El descuento global se suma al precio de cliente? si· bloquea `/sdlc-design SDLC-PRICE-002`
- ¿Dónde se asigna: expediente del cliente (CRM) o Precios? CRM, pero debe existir una lista base (regla «el menú no repite el expediente») · bloquea `/sdlc-design SDLC-PRICE-002`
