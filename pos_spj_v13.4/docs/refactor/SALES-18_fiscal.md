# SALES-18 — Fiscal (POS-18 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-17_document_output.md`.

## Alcance ejecutado

Master prompt §67, fase POS-18: "Invoice request. Status. Errors. Tests." — facturación CFDI.
Ninguna fase anterior había tocado nada fiscal. Investigué primero (agente de research, sin
escritura de archivos) todo el terreno real antes de diseñar.

## Investigación previa

**Dos implementaciones CFDI legacy, independientes, ninguna realmente funcional**:
- `core/services/cfdi_service.py::CFDIService` — la que SÍ está conectada (`core/app_container.py`,
  y `modulos/ventas.py::_generar_factura`, botón F11). **Bug real y confirmado**: `generar_cfdi()`
  llama `new_uuid()` en dos lugares (líneas 129 y 285) pero el archivo nunca importaba esa
  función — cada llamada real fallaba con `NameError`, capturado por un `except Exception`
  genérico que lo devuelve como si fuera un error de negocio cualquiera. Verificado ejecutando el
  método directamente contra una DB desechable, no solo leyendo el código (misma disciplina de
  SALES-9).
- `integrations/cfdi/cfdi_service.py::CfdiService` — una segunda implementación, mejor diseñada
  (patrón `PacAdapter`, `StubPacAdapter`/`FinkokPacAdapter`, guarda antes de timbrar, reintentos),
  pero completamente huérfana — nada la llama en ningún lugar del repositorio.

**Ningún PAC real (Facturama, SW Sapien, Finkok, etc.) está configurado en ningún lado** — solo
llaves de configuración vacías (`cfdi_pac_url`/`cfdi_pac_user`/`cfdi_pac_pass`). Confirmado, no
asumido.

**Hallazgo clave — Customer Master ya construyó exactamente la mitad de datos maestros que esta
fase necesita**: `backend/domain/customers/entities/customer_tax_profile.py::CustomerTaxProfile`
(RFC, razón social, régimen fiscal, uso CFDI por defecto) — real, probado, con su propio
repositorio (`CustomerTaxProfileRepository`), construido en una fase CRM anterior — pero **nada
en ninguna de las dos implementaciones CFDI legacy lo lee jamás**. El diálogo de factura legacy
solo acepta RFC de puño y letra cada vez, sin buscar el perfil fiscal guardado del cliente.

**Confirmación textual de la arquitectura objetivo**: `docs/refactor/customers_crm_master_prompt.md`
§15 dice explícitamente: *"Fiscal administra CFDI. Clientes administra datos maestros. Ventas
conserva snapshots históricos."* — exactamente la frontera que esta fase respeta: Ventas no
reimplementa timbrado, solo solicita y conserva el snapshot histórico de la solicitud.

**El identificador de venta legacy vs. el nuevo `Sale.id` son espacios distintos**:
`CFDIService.generar_cfdi(venta_id)` consulta `ventas WHERE v.id=?` — la tabla legacy, no
`sales`/`sale_lines`. Dado que ninguna venta de la pila nueva se escribe jamás en `ventas`
(confirmado repetidamente desde SALES-6), llamar a ese servicio con un `sale.id` nuevo siempre
devolvería "Venta no encontrada" — no es una integración real posible hoy, ni con el bug
corregido.

## Entregables

### Corrección real, acotada (fuera de la pila nueva, misma disciplina de SALES-9)

Se agregó `from backend.shared.ids import new_uuid` a `core/services/cfdi_service.py` —
una sola línea, corrige el `NameError` confirmado que hacía fallar CADA llamada real a
`generar_cfdi()`. Verificado ejecutándolo contra una DB desechable: antes devolvía
`{"error": "name 'new_uuid' is not defined", ...}`; después genera XML y UUID reales. **No se
conectó este servicio a la pila nueva** (por la razón de espacios de identidad distintos, arriba)
— la corrección beneficia únicamente al botón F11 legacy tal cual existe hoy.

### Dominio

- `InvoiceStatus` enum: `REQUESTED | ISSUED | ERROR | CANCELLED`.
- `SaleInvoiceRequest` — a diferencia de `SalePayment`/`SaleReturn` (inmutables), esta es una
  entidad MUTABLE (como `SaleLine`) porque tiene un ciclo de vida real: `REQUESTED` →
  `ISSUED`/`ERROR`. Guarda el snapshot fiscal (RFC, razón social, uso CFDI) al momento de la
  solicitud — nunca se actualiza retroactivamente si el perfil del cliente cambia después.
- `SaleInvoicePolicy` — solo se puede solicitar factura desde COMPLETED/RETURNED_PARTIAL/
  RETURNED_FULLY; requiere RFC no vacío; rechaza una segunda solicitud mientras una sigue
  `REQUESTED` (`InvoiceAlreadyPendingError`) — un reintento real primero debe resolver
  (issued/error) la anterior.
- `Sale.request_invoice()` / `mark_invoice_issued()` / `mark_invoice_error()`.
- Tres eventos nuevos: `SaleEvents.INVOICE_REQUESTED`/`INVOICE_ISSUED`/`INVOICE_ERROR`.

### Esquema

`sale_invoice_requests` (mirrors `sale_payments`/`sale_returns`) — migración 204.

### Infraestructura

`backend/infrastructure/integrations/sales_fiscal_client.py::SalesFiscalClient` — el lado
faltante: lee el `CustomerTaxProfile` REAL de un cliente asignado (RFC/razón social/uso CFDI por
defecto), delegando por completo en el repositorio ya existente de Customer Master — nunca
reimplementa almacenamiento fiscal propio.

### Aplicación

`backend/application/sales/use_cases/invoice_use_cases.py`:
- `RequestInvoiceUseCase` — resuelve RFC/razón social/uso CFDI en este orden: argumentos
  explícitos del llamador → `CustomerTaxProfile` real si la venta tiene cliente asignado →
  default "público en general" (`XAXX010101000`, el mismo RFC genérico que ya usa el diálogo
  legacy — reutilizado, no inventado).
- `MarkInvoiceIssuedUseCase`/`MarkInvoiceErrorUseCase` — la API de resolución real que un futuro
  bounded context Fiscal (o una reconciliación manual) llamaría al tener un resultado real de
  timbrado — nunca invocadas especulativamente por esta fase.

**Permisos**: cero cambios — `SalesPermissions.INVOICE_REQUEST` (`"POS.factura.solicitar"`) ya
existía desde SALES-2, sin consumidor hasta ahora.

### Tests

18 nuevos en `tests/unit/test_sales_invoicing.py` (dominio: estado no facturable rechazado, RFC
vacío rechazado, segunda solicitud pendiente rechazada, `mark_issued`/`mark_error` transicionan
correctamente, reintento después de error permitido, no se puede resolver una solicitud ya
resuelta; aplicación: permiso exigido, falla para venta no completada, default RFC público en
general sin cliente, **resuelve el perfil fiscal REAL de Customer Master cuando hay cliente
asignado** (verificado con `CustomerTaxProfileRepository` real, no un doble), argumentos
explícitos tienen prioridad sobre el perfil, segunda solicitud pendiente falla, evento emitido,
`mark_issued`/`mark_error` exigen permiso y resuelven correctamente, reintento tras error deja
ambas solicitudes en el historial con sus estados reales, id de solicitud desconocido falla
explícito). Una corrección de fixture necesaria en la primera corrida: dos tests asignaban el
cliente DESPUÉS de completar la venta — `CustomerAssignmentPolicy` correctamente rechaza asignar
cliente a una venta ya COMPLETED (comportamiento de dominio correcto, no un bug), corregido
asignando antes del checkout.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se construyó ningún timbrado real.** Ningún PAC está configurado en este repositorio;
  `MarkInvoiceIssuedUseCase` es la API que un futuro bounded context Fiscal llamaría, no algo que
  esta fase invoca automáticamente con un resultado inventado.
- **No se conectó `CFDIService` (corregida) a la pila nueva** — opera sobre un espacio de
  identidad de venta legacy distinto (`ventas.id`), incompatible con `Sale.id` de la pila nueva.
- **No se tocó `modulos/ventas.py`.** El botón F11/`_generar_factura` sigue llamando
  `CFDIService` directamente con captura de RFC de puño y letra — ahora sin el `NameError`, pero
  sin buscar `CustomerTaxProfile` tampoco (esa mejora solo existe en la pila nueva).
- **No se construyó el `CfdiService` huérfano ni se adoptó su patrón `PacAdapter`** — código real
  pero nunca probado contra una cuenta PAC real; no es una base confiable para construir encima.

## Siguiente fase

El master prompt continúa con POS-19 (UI decomposition) — confirmar alcance con el usuario antes
de asumir.
