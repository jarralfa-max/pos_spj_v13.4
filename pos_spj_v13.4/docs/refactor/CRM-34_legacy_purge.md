# CRM-34 — Purga de legacy: `core/services/cliente_service.py` eliminado

Fecha: 2026-08-16. Séptima fase del cut-over completo (mapa Fase 0 §9
"Legacy purge").

## Qué se eliminó

`core/services/cliente_service.py` (`ClienteService`) — confirmado por
dos auditorías independientes (Fase 0 de esta sesión y una inspección
directa del archivo) como código sin consumidores de producción:

- Su único caller real, el diálogo legacy `DialogoCliente`
  (`modulos/dialogs/cliente_*.py`), ya fue retirado en CRM-24
  (`docs/refactor/CRM-24_retiro_modulo_legacy.md`) — `guardar_formulario()`,
  el método más grande de la clase (duplicado, asignación de tarjeta,
  patrón UC-con-fallback-a-SQL), servía exclusivamente a esa UI ya
  inexistente.
- Su única capacidad con valor de negocio independiente,
  `get_crm_loyalty_summary()`, es funcionalmente redundante:
  `LoyaltyCustomerSummaryQuery` (la misma clase que envolvía) ya está
  wireada directamente en `Customer360QueryService` → el Expediente del
  cliente (pestaña "Integraciones") — un usuario real ya ve exactamente
  esos mismos datos por esa vía. No se perdió ninguna capacidad, solo una
  envoltura sin usuarios.
- El único archivo que lo importaba fuera de sí mismo era un test
  (`tests/integration/customers/test_crm_21_read_path_wiring.py`,
  `TestFidelidadClienteServiceCrmLoyaltySummary`) — eliminado junto con la
  clase, con una nota explicando por qué (mismo criterio que el trailing
  comment ya existente en `tests/integration/test_customer_history_query_service.py`
  para un caso análogo).

Actualizados también (per su propia regla "cada entrada debe desaparecer
de aquí, no solo bajar de número"):
- `tests/architecture/allowlists.py::CUSTOMERS_CRM_LEGACY_CONSUMERS`
- `tests/architecture/customers_crm_guardrails.py::LEGACY_CUSTOMER_FILES`

## Qué NO se eliminó en esta fase (identificado, no purgado)

`core/use_cases/cliente.py` (`GestionarClienteUC`) — la auditoría de
Fase 0 lo encontró "wireado pero huérfano": `core/app_container.py` sigue
construyendo `self.uc_cliente = GestionarClienteUC.desde_container(self)`,
pero su único llamador real era `ClienteService.guardar_formulario()`
(ahora eliminado) — sin ese caller, `container.uc_cliente` queda sin
ningún consumidor de producción conocido. Se dejó fuera de esta fase
deliberadamente: su purga completa toca más superficie que
`ClienteService` (la construcción en `app_container.py`, el re-export en
`application/use_cases/__init__.py`, y dos archivos de test propios —
`tests/test_uc_cliente.py`/`tests/test_application_layer.py` — que
prueban la clase de forma aislada, no solo vía `ClienteService`) y merece
su propia verificación cuidadosa, no un borrado apurado al cierre de una
sesión ya larga. Sigue en `LEGACY_CUSTOMER_FILES`/
`CUSTOMERS_CRM_LEGACY_CONSUMERS`, sin cambios.

`repositories/cliente_repository.py` y `api/routers/clientes.py` — ambos
confirmados como dependencias de producción REALES (Ventas checkout, API
REST de WhatsApp) — no son candidatos de purga, permanecen intactos y
correctamente listados en el allowlist.

## Verificación

```bash
python -m pytest tests/integration/customers/test_crm_21_read_path_wiring.py \
  tests/architecture/test_customers_crm_*.py -v
```
29 tests pasando, incluido el guardrail que verifica el allowlist legacy
(`test_customers_crm_legacy_allowlist_is_empty.py` — confirma que la
entrada retirada realmente desapareció del registro, no solo que el
archivo ya no existe).

Chequeo de sintaxis repo-wide: sin errores tras la eliminación.
