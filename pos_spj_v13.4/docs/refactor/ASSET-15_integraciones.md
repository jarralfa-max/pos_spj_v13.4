# ASSET-15 — Integraciones (Activos / EAM)

Ejecutado: 2026-09-02. §28, §52-58 del prompt maestro.

## Alcance de esta fase dado que no hay infraestructura todavía

§52-58 del prompt maestro describe integraciones con Finanzas, Compras, Tesorería, Inventario, RRHH, Configuración y BI. La mitad de eso (Finanzas, Tesorería) ya está resuelta arquitectónicamente desde ASSET-1/ASSET-3: son los eventos de `AssetEvents` + el mapa de frontera (`assets_finance_boundary_map.md`) + los guardrails que prohíben llamarlas directamente. Lo que faltaba formalizar era el lado **consumidor**: los contratos que Activos necesita de Compras/RRHH/Configuración/Document Output para no duplicar sus catálogos (§28, §56, §57) ni reimplementar su lógica (§49, §51).

## Qué se construyó

`backend/domain/assets/integration_ports.py` — 5 Protocols de solo consulta/gateway, ninguno con implementación (los adaptadores concretos los construye/wire una fase de bootstrap futura, mismo patrón que `whatsapp_service/erp/erp_ports.py` ya usa en este repo para envolver `ERPBridge` sin reimplementar su lógica):

| Port | Frontera que protege |
|---|---|
| `SupplierLookupPort` (+ `SupplierRef`) | §28 — Compras es dueño del proveedor maestro; Activos solo lee un ref delgado para proveedores externos de mantenimiento |
| `EmployeeLookupPort` (+ `EmployeeRef`) | §56 — RRHH es dueño del empleado; Activos solo lee un ref para custodios/responsables/técnicos |
| `DeviceRegistrationLookupPort` | §57 — Configuración/Device Management es dueño del driver físico (puerto COM, etc.); Activos solo referencia el id de registro, nunca lo administra |
| `DocumentStorageGatewayPort` | §42-43 — formaliza el contrato que `AssetDocument.storage_reference` (ASSET-9) ya asumía; Activos nunca guarda una ruta de archivo cruda |
| `PrintJobGatewayPort` | §49, §51 — toda impresión (etiquetas, PDF) pasa por Document Output, nunca por una librería de PDF directa (el anti-patrón FPDF del legacy `modulos/activos.py`) |

## Verificación de completitud del catálogo de eventos (§87)

En vez de reescribir el catálogo, se agregó un test parametrizado que confirma que los eventos canónicos de cada fase (ASSET-3 a ASSET-13) siguen registrados en `ALL_ASSET_EVENTS` — una red de seguridad barata contra un typo o una omisión accidental en alguna edición futura de `events.py`.

## Explícitamente fuera de alcance

No se construyeron adaptadores concretos (`ErpBridgeCustomersApiClient`-style) para ninguno de estos 5 ports — eso requiere que exista el módulo consumido (p. ej. un `SupplierDirectoryService` real de Compras) y una fase de bootstrap/composición que los conecte, symétrica a `WhatsAppCompositionRoot._try_build_erp_bridge()`. Tampoco se construyeron `event_handlers/` de aplicación que efectivamente consuman los eventos de Finanzas (`ASSET_CAPITALIZATION_ACCEPTED`/`REJECTED`) para actualizar `AssetCapitalizationProposal` — la entidad tiene los métodos (`approve()`/`reject()`/`mark_posted()`, ASSET-10) pero nada los invoca todavía.

## Tests

`tests/unit/assets/test_integration_ports.py` — `SupplierRef`/`EmployeeRef` son inmutables (frozen dataclass), 20 eventos representativos (uno o más por cada fase ASSET-3 a ASSET-13) confirmados presentes en `ALL_ASSET_EVENTS`.

**Conteo total de la suite de Activos tras ASSET-1 a ASSET-15**: 181 tests (unitarios + arquitectura) passed, 2 skipped (intencional) — todo en verde.

## Siguiente fase

Con ASSET-14/15 cerradas, la capa de lectura y los contratos de integración existen — pero **sigue sin existir ninguna capa de escritura ejecutable**: no hay `backend/application/assets/use_cases/` (las mutaciones — crear activo, asignar, transferir, completar mantenimiento, etc. — no tienen ningún punto de entrada invocable), no hay `backend/infrastructure/db/repositories/assets/` (los ports de escritura no tienen implementación), no hay `assets_schema.py`. Con 15 fases construidas y CERO capacidad de persistir un cambio, este es ahora el bloqueador más claro para que cualquier parte de Activos sea funcional de verdad — más urgente que seguir con ASSET-16 (UI), que necesitaría use cases reales para tener algo que llamar.
