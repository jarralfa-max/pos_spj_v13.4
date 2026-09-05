# ASSET-23 — Reporte de disposición de legacy (Activos / EAM)

Ejecutado: 2026-09-02. §109, §115 del prompt maestro.

## Ninguna eliminación se ejecutó en esta fase

Esta fase produce el **reporte de disposición** que el prompt maestro pide en su tabla obligatoria (§115) — no borra nada. `modulos/activos.py` y `core/services/asset_service.py` siguen siendo la única implementación funcional de Activos en producción (confirmado en ASSET-22: wiring de menú, DI, y **un job programado mensual de depreciación** dependen de ellos). Borrarlos ahora rompería la aplicación real. El objetivo de este documento es dejar el mapa completo de qué bloquea cada eliminación futura, no ejecutarla.

## Corrección a la auditoría ASSET-0: la tabla `assets` NO está huérfana

ASSET-0 clasificó el par de tablas `assets`/`asset_maintenance` (esquema paralelo en inglés, `m000_base_schema.py` líneas 1506/1524) como "no referenciado por AssetService, candidato a DELETE pendiente de confirmar 0 referencias". Esta fase hizo esa confirmación exhaustiva y **el resultado corrige el hallazgo**:

- **`asset_maintenance`**: confirmado sin ninguna referencia real (`FROM`/`INTO`) en todo el repo — solo aparece en la lista de tablas de la herramienta histórica de cutover UUID (`migrations/standalone/_cutover_spec_generated.py`) y en el guardrail de identidad born-clean (`test_clean_birth_guardrails.py`). **Sí es candidato real a DELETE.**
- **`assets`**: **SÍ tiene un consumidor real y activo** — `core/services/enterprise/finance_service.py` (líneas 244-249) hace `SELECT COALESCE(SUM(valor_actual), 0) ... FROM assets WHERE estado != 'dado_baja'` para calcular "Activos fijos" en un reporte de balance financiero. No es el mismo servicio que `AssetService` (que usa la tabla `activos`, con "a" minúscula, en español) — son dos tablas completamente distintas (`assets` en inglés vs. `activos` en español) leídas por dos servicios financieros distintos (`finance_service.py` enterprise vs. `treasury_service.py`) para el mismo propósito (valor de activos fijos en reportes). **`assets` no puede eliminarse sin antes migrar esa lectura.**

Esto significa que hoy existen **tres fuentes de verdad desconectadas** para "valor de activos fijos" en este repositorio:

| Fuente | Tabla | Consumidor | Detectado en |
|---|---|---|---|
| Legacy operativo (español) | `activos` | `core/services/finance/treasury_service.py` | ASSET-22 |
| Legacy paralelo (inglés, huérfano de Activos) | `assets` | `core/services/enterprise/finance_service.py` | ASSET-23 (esta fase) |
| Canónico financiero | `fixed_assets` (migración 083) | `backend.domain.finance.entities.fixed_asset.FixedAsset` + `FixedAssetQueryService` | ASSET-0 |

Ninguna de las tres fuentes coincide necesariamente en cifra — esto es deuda técnica real de reconciliación financiera que existía antes de esta pipeline y que esta pipeline no introdujo, pero que si se ignora, cualquier corte futuro de Activos (o de Finanzas) puede cambiar silenciosamente un número de balance que alguien ya está reportando.

## Cadena de código muerto adicional encontrada

`backend/application/commands/asset_commands.py` (flagged en ASSET-0 como "probable DELETE_DUPLICATE") tiene, de hecho, dos referentes: `backend/application/use_cases/complete_maintenance_use_case.py` y `backend/application/use_cases/schedule_maintenance_use_case.py`. **Ninguno de los dos tiene ningún consumidor externo** (ni UI, ni API, ni test más allá de sí mismos) — así que la cadena completa (`asset_commands.py` → esos 2 use cases → nada) está muerta, confirmando la clasificación original con más detalle del que ASSET-0 tenía. `backend/application/queries/asset_query_service.py`'s `AssetQueryService` también se confirma huérfano: solo se re-exporta desde `backend/application/queries/__init__.py`, nada lo instancia (una búsqueda inicial que sugería lo contrario resultó ser un falso positivo por coincidencia de substring con `FixedAssetQueryService`, un servicio real y distinto).

## Tabla de disposición (§115)

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|---|---|---|---|
| `modulos/activos.py` | `frontend/desktop/modules/assets/` (ASSET-16-19, solo lectura hoy) | NO ELIMINAR — bloqueado por wiring de menú + único CRUD funcional | `interfaz/main_window.py`, `core/ui/module_loader.py` |
| `core/services/asset_service.py` | `backend/domain/assets/` + `backend/application/assets/` (dominio y lectura listos; sin casos de uso de escritura) | NO ELIMINAR — bloqueado por job de depreciación mensual + único CRUD funcional | `core/app_container.py` (DI + scheduler) |
| Tabla `activos` | `fixed_assets` (canónico, ya existe) + nuevo esquema de dominio EAM (no construido) | NO ELIMINAR — `treasury_service.py` la lee para reportes reales | `core/services/asset_service.py`, `core/services/finance/treasury_service.py` |
| Tabla `mantenimientos` | Nuevo esquema `MaintenanceWorkOrder`/`MaintenancePlan` (dominio listo, sin persistencia) | NO ELIMINAR — usada activamente por `AssetService` | `core/services/asset_service.py` |
| Tabla `activos_depreciacion` | `asset_depreciation_entries` (canónico) | NO ELIMINAR — usada activamente por `AssetService` | `core/services/asset_service.py` |
| Tabla `assets` (huérfana de Activos, con "s") | `fixed_assets` (canónico) | **NO ELIMINAR — corrección de ASSET-0**: consumida por `finance_service.py` enterprise | `core/services/enterprise/finance_service.py` |
| Tabla `asset_maintenance` | Ninguno (nunca tuvo datos reales) | **DELETE candidato confirmado** — cero referencias reales en todo el repo | Ninguno |
| `backend/application/commands/asset_commands.py` | Ninguno | **DELETE_DUPLICATE candidato confirmado** — cadena completa muerta | Ninguno externo |
| `backend/application/use_cases/complete_maintenance_use_case.py` | `MaintenanceWorkOrder.complete()` (ASSET-6, ya existe en dominio) | **DELETE_DUPLICATE candidato confirmado** | Ninguno externo |
| `backend/application/use_cases/schedule_maintenance_use_case.py` | `MaintenanceWorkOrder.schedule()` (ASSET-6, ya existe en dominio) | **DELETE_DUPLICATE candidato confirmado** | Ninguno externo |
| `backend/application/queries/asset_query_service.py` | `AssetDetailQueryService`/`AssetDirectoryQueryService` (ASSET-14, ya existen) | **DELETE_DUPLICATE candidato confirmado** | Ninguno externo (solo re-exportado, no usado) |
| `tests/architecture/test_clean_birth_guardrails.py::test_activos_tables_are_born_clean_uuid_identity` | Un guardrail equivalente sobre el nuevo esquema (fase de infraestructura futura) | Retirar/actualizar junto con el legacy, no antes | — |

## Por qué no se eliminó nada de lo "confirmado" tampoco

Aunque 4 elementos de la tabla arriba tienen "cero consumidores externos" confirmado, **esta sesión no los borró**. Cambios destructivos de código no solicitados explícitamente no son parte del alcance de "continuar con las fases del prompt maestro" — el propio §17 checklist pre-merge de `CLAUDE.md` y las reglas de seguridad de este entorno piden confirmación antes de acciones difíciles de revertir. Este reporte dejó el mapa exacto; borrar esos 4 archivos es una acción de una sola línea de confirmación si el usuario la pide explícitamente en una sesión futura.

## Siguiente fase

ASSET-24 — Validación final (construida en la misma sesión, ver doc propio).
