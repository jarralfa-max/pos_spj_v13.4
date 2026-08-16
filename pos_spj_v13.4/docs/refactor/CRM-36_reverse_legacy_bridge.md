# CRM-36 — Fase 2 (identidad única): el bridge inverso que faltaba

Fecha: 2026-08-16. Continuación del cut-over tras el reporte de cierre
(CRM-35), a petición explícita del usuario de retomar "FASE 2 — IDENTIDAD
ÚNICA DE CLIENTE" del prompt maestro.

## Por qué esta pieza y no una migración de esquema completa

Fase 2 pide, literalmente, migrar Ventas/WhatsApp/Finanzas/Delivery/
Fidelidad/CRM a referenciar `customer_id` en cualquier FK. Hecho al pie
de la letra hoy significaría reescribir el esquema de ~17 tablas activas
(`ventas`, `cuentas_por_cobrar`, `delivery_orders`, `loyalty_*`,
`pedidos_whatsapp`, etc.) y cada consumidor que las escribe — una
migración de varias semanas, no algo defendible en una sola sesión sin
QA en vivo sobre un flujo de ingresos real (checkout).

En vez de eso, esta fase ataca la causa raíz que el propio CRM-32 ya
había documentado como límite explícito: el bridge CRM-21
(`customers.legacy_customer_id`) solo funciona en una dirección
(legacy → nuevo). Un cliente creado ÚNICAMENTE en el Customer Master
—vía la página "Nuevo cliente" del CRM— nunca podía ser encontrado ni
usado por Ventas, porque no existe la dirección inversa. Cerrar esa
brecha es el requisito real para que "identidad única" sea cierto en la
práctica: hoy, sin importar por qué puerta entra un cliente al sistema,
termina siendo transaccionable desde cualquier módulo.

## Qué se construyó

- **`EnsureLegacyCustomerBridgeUseCase`** (nuevo,
  `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py`):
  dado un `customer_id`, si ya tiene `legacy_customer_id` lo retorna sin
  tocar nada (nunca pisa un bridge existente, sin importar de qué
  dirección vino). Si no lo tiene, crea una fila `clientes` real
  (nombre = `display_name`, teléfono/email del contacto primario si
  existe) y apunta `customers.legacy_customer_id` a ella — la única
  excepción sancionada a que esa columna sea de solo-escritura-en-creación
  (mismo criterio que el propio `ResolveLegacyCustomerUseCase` ya usa
  para leer `clientes` directamente).
- **`ModuloVentas.aplicar_contexto`** (CRM-32): ya no muestra "cliente sin
  registro en Ventas" — ahora crea el bridge inverso al vuelo, así que
  "Nueva venta" desde el Expediente del cliente SIEMPRE funciona.
- **`ModuloVentas.buscar_cliente`**: cuando la búsqueda legacy no
  encuentra nada, intenta también en el Customer Master
  (`CustomerLookupQueryService`, permission-gated vía
  `container.customer_authorization_policy` ya wireado desde CRM-25) y,
  si encuentra, asegura el bridge inverso antes de seleccionar. La
  búsqueda legacy sigue siendo la ruta primaria sin ningún cambio — el
  fallback solo se consulta cuando esa ruta ya falló, cero riesgo para
  cualquier cliente que ya era encontrable hoy.

## Explícitamente NO tocado en esta fase

- **El esquema de `ventas`/`cuentas_por_cobrar`/`delivery_orders`/
  `loyalty_*` sigue en `cliente_id` legacy** — esta fase resuelve
  identidad en el punto de entrada (búsqueda/selección), no re-arquitecta
  las tablas de escritura. Ver CRM-27/CRM-35 §11 para el resto de la
  deuda de esquema ya documentada.
- **WhatsApp/Delivery/Fidelidad**: no se tocaron. El mismo patrón
  (bridge inverso + fallback de búsqueda) es aplicable ahí, pero cada uno
  tiene su propio punto de entrada de identidad (número de teléfono para
  WhatsApp, no un campo de búsqueda de texto) — requiere su propio diseño,
  no una copia mecánica de esta fase.
- **El permiso `CLIENTES.buscar` para el rol de caja**: dato/admin-UI, no
  código — mismo caveat que CRM-25 ya dejó para `CUSTOMERS_VIEW`/
  `CUSTOMERS_CREATE`. Sin ese grant, el fallback simplemente no encuentra
  nada extra (degrada silenciosamente, no bloquea).

## Verificación

```bash
python -m pytest tests/integration/customers/test_crm_21_legacy_identity_bridge.py \
  tests/test_ventas_customer_dialog_regression.py \
  tests/integration/customers/test_customer_360_application.py \
  tests/architecture/test_customers_crm_*.py -v
```
66 tests pasando (14 nuevos de esta fase: 5 de
`EnsureLegacyCustomerBridgeUseCase`, 1 reescrito en `aplicar_contexto`
para reflejar el nuevo comportamiento, 4 del fallback de búsqueda), cero
regresiones.

Nota de entorno: correr estos 4 archivos juntos en un orden específico
dispara un fallo de descubrimiento de fixtures de pytest
(`full_crm_conn` no encontrado) — confirmado como un artefacto de orden
de colección preexistente de este repo (reordenar los mismos archivos lo
hace desaparecer, cada archivo pasa limpio en aislamiento y en otras
combinaciones) — no relacionado con el código de esta fase.

## Siguiente candidato natural dentro de Fase 2

Con el bridge ahora bidireccional, el mismo patrón (fallback de búsqueda
+ bridge-on-demand) es aplicable a WhatsApp (`erp/bridge.py::
find_cliente_by_phone`) para que un cliente nativo del CRM con teléfono
registrado también sea encontrable desde un chat entrante — no
implementado aquí, siguiente fase candidata si se continúa.
