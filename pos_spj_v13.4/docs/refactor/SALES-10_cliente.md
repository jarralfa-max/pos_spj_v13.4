# SALES-10 — Cliente (POS-10 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-9_reservas_inventario.md`.

## Alcance ejecutado

Master prompt §67, fase POS-10: "Search. Assign. Quick create. Loyalty card scan. Tests."
Secciones 21-23: Ventas no es dueño de identidad de cliente (§6) — el POS debe **consumir**
`CustomerLookupQueryService`/`CreateQuickCustomerUseCase`/`AssignCustomerToSaleUseCase`, nunca
reconstruir lógica de Clientes/CRM. Dado que el bounded context de Customer Master/CRM ya está
extensamente construido en este repositorio (CRM-0 a CRM-42+, ver memoria
`crm_enterprise_transformation`), investigué primero qué existe realmente antes de diseñar
nada — patrón que también encontró un gap real de seguridad, no solo de integración.

## Hallazgos de investigación (antes de escribir código)

1. **`CustomerLookupQueryService` real ya existe** (`backend/application/customers/queries/
   customer_lookup_query_service.py`), deliberadamente sin scope-restriction (a diferencia de
   casi todo lo demás en Customer Master) — su propio docstring cita literalmente la sección 21
   del master prompt como la razón: un cajero necesita encontrar cualquier cliente activo, no
   solo los de su propio scope. Gateado por `CustomerPermissions.SEARCH`. Retorna
   `CustomerLookupResult` (DTO plano). **No se necesitó construir nada nuevo para "Search"** —
   solo exponerlo a través de un cliente delgado.

2. **`CreateCustomerUseCase` canónico de Customer Master** (`backend/application/customers/
   use_cases/lifecycle_use_cases.py`, distinto del más simple que `modulos/ventas.py` ya usa
   hoy — mismo patrón de "dos implementaciones" que SALES-6/7 ya encontraron para
   Commands/Catálogo) acepta `display_name` + `phone_e164` opcional sin ningún otro campo
   requerido — coincide exactamente con la sección 22. **Verificado leyendo el archivo
   completo antes de conectarlo**: no toca ninguna tabla de fidelidad/tarjeta/puntos — la
   sección 22 ("crear cliente no implica automáticamente membresía/tarjeta/puntos") ya es
   cierta de este use case, no algo que Sales deba prevenir. El teléfono, sin embargo, **no
   se persiste** en `CreateCustomerUseCase` mismo — vive en la entidad hija
   `CustomerContactPerson`, requiere una segunda llamada a `AddCustomerContactUseCase`.

3. **El escaneo de tarjeta de fidelidad NUNCA toca la tabla nueva `customers`.** Investigación
   confirmó que los tres caminos reales de escaneo en este repositorio
   (`ClienteRepository.get_by_scanner`, `CardBatchEngine.buscar_tarjeta`,
   `LoyaltyService.resolve_scan`) operan exclusivamente sobre las tablas legacy `clientes`/
   `tarjetas_fidelidad`. Ninguno fue migrado durante CRM-24 (confirmado en la propia memoria de
   CRM). Esto significa que cualquier resultado de escaneo de tarjeta produce un `clientes.id`
   legacy, nunca un `customers.id` de Customer Master.

4. **Puente ya existe**: `ResolveLegacyCustomerUseCase` (CRM-21,
   `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py`) traduce un
   `clientes.id` legacy a un `customers.id` real, creando el puente de forma perezosa si no
   existe. Nunca lanza excepción (diseñado para no fallar una venta por un hueco de bridging).

5. **Hallazgo de seguridad real, no solo de integración**: `AssignCustomerToSaleUseCase`
   (construido en SALES-6) llamaba `sale.assign_customer(customer_id)` con **cero validación
   de existencia** — aceptaba cualquier string con forma de UUIDv7, real o no. Esto quedó
   expuesto al construir los flujos de búsqueda/creación/escaneo, que ahora sí producen ids
   reales que el caso de uso debería verificar.

## Entregables

**Dominio**: `SaleCustomerNotFoundError` (nueva excepción) en
`backend/domain/sales/exceptions.py`. **Corrección de un olvido de SALES-9**: al agregar esta
excepción a la tabla de mapeo de `result.py`, encontré que `InventoryReservationFailedError`
(SALES-9) nunca se había agregado a `_ERROR_CODES` — caía silenciosamente al fallback genérico
`"VALIDATION"`. Corregido en esta fase (ningún test existente dependía del código anterior).

**Infraestructura**: `backend/infrastructure/integrations/sales_customer_client.py::
SalesCustomerClient` — mirrors `sales_inventory_client.py`: `search()` (delega a
`CustomerLookupQueryService`, sin gate propio de Sales — el permiso `CLIENTES.buscar` ya se
aplica dentro), `quick_create()` (delega a `CreateCustomerUseCase` de Customer Master +
`AddCustomerContactUseCase` si hay teléfono), `exists()` (chequeo directo, sin gate — una
validación booleana, no una lectura de datos sensibles), `resolve_legacy_customer()` (envuelve
`ResolveLegacyCustomerUseCase`), `lookup_by_card()` (envuelve `ClienteRepository.get_by_scanner`,
retorna explícitamente un id **legacy** — la responsabilidad de traducirlo recae en el
llamador, nunca implícita).

**Aplicación**:
- `AssignCustomerToSaleUseCase` (SALES-6) **modificado**: ahora valida existencia real vía
  `SalesCustomerClient.exists()` antes de asignar — cierra el hallazgo 5. Limpiar cliente
  (`customer_id=None`) sigue sin requerir el chequeo (no hay nada que validar).
- `QuickCreateCustomerForSaleUseCase` (nuevo, `backend/application/sales/use_cases/
  customer_use_cases.py`) — delgado, delega completo a `SalesCustomerClient.quick_create`.
- `ScanLoyaltyCardForSaleUseCase` (nuevo) — la sección 21 describe "escanear tarjeta" como una
  sola acción real de POS, no dos pasos separados: busca por código, **traduce obligatoriamente**
  vía el puente legacy→Customer Master, y asigna a la venta reutilizando
  `AssignCustomerToSaleUseCase` (sin duplicar su lógica de validación/eventos).

**Sin nuevo código de permiso de Sales para "buscar"**: la autorización de búsqueda ya la
impone `CustomerLookupQueryService` internamente (`CustomerPermissions.SEARCH`); Sales no
necesita un código paralelo. "Quick create" y "Assign" (parte del escaneo) reutilizan los gates
ya establecidos de Customer Master y de Sales respectivamente, sin inventar uno nuevo — mismo
criterio que SALES-6 ya aplicó a `AssignCustomerToSaleUseCase`.

**Tests** (12 nuevos en `tests/unit/test_sales_customer_integration.py`, todos verdes en la
primera corrida — la investigación previa evitó cualquier ciclo de depuración de esquema; 221
en total en la suite SALES-0..10 combinada, cero regresiones tras corregir 1 fixture de una
fase anterior): búsqueda encuentra clientes reales, creación rápida con/sin teléfono (incluye
verificación explícita de que NO se crea ninguna tabla de fidelidad), asignación de cliente
real exitosa, **asignación de cliente inexistente rechazada** (regresión directa del hallazgo
5), escaneo de tarjeta por código QR y por teléfono resuelve y asigna correctamente, **escaneo
repetido de la misma tarjeta es idempotente** (bridging a la misma fila de `customers`, no una
nueva cada vez), tarjeta desconocida falla limpiamente.

**Regresión en 1 fixture de fase anterior, corregida**: `test_sales_use_cases.py::
TestCartUseCases::test_assign_and_clear_customer` (SALES-6) asignaba un `new_uuid()` sin fila
real — rota por el nuevo chequeo de existencia. Corregida creando un cliente real vía
`create_customers_crm_schema` + `QuickCreateCustomerForSaleUseCase` en el propio test, mismo
patrón que la corrección de fixtures de SALES-9 para inventario.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se migró el escaneo de tarjeta a Customer Master.** `ScanLoyaltyCardForSaleUseCase`
  puentea el resultado legacy hacia un `customers.id`, pero la búsqueda en sí sigue
  consultando `clientes`/futuras `tarjetas_fidelidad` — exactamente como CRM-21/24 ya
  documentaron que sigue siendo el único camino real; no era competencia de esta fase
  reconstruir el sistema de tarjetas.
- **No se conectó nada de esto a `modulos/ventas.py`.** El diálogo de cliente rápido, la
  búsqueda y el escaneo de tarjeta reales de la UI siguen usando sus propios caminos legacy
  (`_cli_repo`, `_customer_lookup_svc`, `card_batch_engine`) sin cambios.
- **`EvaluateCustomerBenefitsQuery`/`LoyaltySummaryQuery`** (§23, mostrar nivel/puntos/
  beneficios) no se construyeron — esta fase se limitó a los 4 verbos explícitos de POS-10
  (Search/Assign/Quick create/Loyalty card scan); mostrar fidelidad es una superficie de
  lectura adicional, candidata a una fase futura si el usuario la pide por nombre.

## Siguiente fase

El master prompt continúa con POS-11 (Pricing y beneficios: Effective price, Promotions,
Loyalty, Coupons, Vouchers, Tests). Confirmar alcance con el usuario antes de asumir.
