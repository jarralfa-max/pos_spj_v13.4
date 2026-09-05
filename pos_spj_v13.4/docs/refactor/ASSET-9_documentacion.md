# ASSET-9 — Documentación, garantías y seguros (Activos / EAM)

Ejecutado: 2026-09-02. §40-43 del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_document.py` — `AssetDocument` (§42-43). `storage_reference` es un token opaco de un `DocumentStorageGateway` futuro (infraestructura, fase posterior) — **nunca una ruta de archivo cruda guardada directamente**, tal como exige §42. `create()` valida `mime_type`, `size_bytes` (positivo y bajo un tope de 25 MB) y `file_hash` (§43: "validar MIME, validar tamaño, calcular hash"). Nuevo enum `AssetDocumentType` (INVOICE/MANUAL/WARRANTY/INSURANCE/PHOTO/CERTIFICATE/SERVICE_REPORT/REGISTRATION/OWNERSHIP/OTHER).

`backend/domain/assets/entities/asset_warranty.py` — `AssetWarranty` (§40). Reutiliza `AssetWarrantyStatus` (ya existía desde ASSET-3, donde vivía como campo resumen en `Asset`). `refresh_status()` deriva ACTIVE/EXPIRING/EXPIRED de las fechas; `VOID` es "pegajoso" — una vez anulada por `void()`, `refresh_status()` nunca la reactiva. `is_expiring(within_days=30)` es la base para alertas de vencimiento (§40: "Alertar antes de vencimiento").

`backend/domain/assets/entities/asset_insurance_policy.py` — `AssetInsurancePolicy` (§41). Usa `Money` (de `backend.domain.finance.value_objects.money`, mismo patrón que el resto del dominio Activos) para `insured_value` — Activos documenta la póliza, **nunca la gestiona contablemente** (§41 lo dice explícitamente). Nuevo enum `AssetInsuranceStatus` (ACTIVE/EXPIRING/EXPIRED/CANCELLED); `cancel()` también es "pegajoso" frente a `refresh_status()`.

Excepciones nuevas: `AssetDocumentNotFoundError`, `AssetWarrantyNotFoundError`, `AssetInsuranceNotFoundError`. Eventos nuevos: `ASSET_DOCUMENT_UPLOADED`, `ASSET_DOCUMENT_DELETED`, `ASSET_WARRANTY_REGISTERED`, `ASSET_WARRANTY_EXPIRING`, `ASSET_WARRANTY_EXPIRED`, `ASSET_INSURANCE_REGISTERED`, `ASSET_INSURANCE_CANCELLED` (§87 no los enumera; se agregaron por el mismo criterio de fases anteriores). Ports: `AssetDocumentRepositoryPort`, `AssetWarrantyRepositoryPort`, `AssetInsurancePolicyRepositoryPort`.

## Tests

`tests/unit/assets/test_asset_documentation.py` — documento (tamaño excedido falla, tamaño cero falla), garantía (fechas invertidas falla, `refresh_status` en sus tres estados, `void()` pegajoso), póliza (valor asegurado no positivo falla, cancelar, cancelar dos veces falla, expira tras la fecha, `cancel()` pegajoso frente a `refresh_status`).

**Conteo total de la suite de Activos tras ASSET-1 a ASSET-9**: 106 tests (unitarios de `tests/unit/assets/` + arquitectura de `tests/architecture/test_assets*.py`/`test_asset_*.py`) passed, 2 skipped (intencional) — todo en verde.

## Siguiente fase

Todavía sin infraestructura de persistencia para ninguna entidad de ASSET-3 a ASSET-9 (repository ports son solo `Protocol`). Antes de seguir con ASSET-10 (mejoras/capitalización propuesta) conviene evaluar una fase de infraestructura/persistencia — mismo pendiente señalado desde `ASSET-6_mantenimiento.md`, ahora con 9 fases de dominio acumuladas sin poder ejecutarse contra una base de datos real.
