# ASSET-13 — Etiquetas / QR (Activos / EAM)

Ejecutado: 2026-09-02. §14, §49-51 del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_tag.py` — `AssetTag`. **El QR nunca expone el UUID interno del activo** (§14, §50): `qr_public_token` es un identificador opaco distinto de `asset_id` y de `id` de la propia etiqueta, generado con el mismo `new_uuid()` canónico pero nunca usado para resolver el activo fuera de la ruta de resolución de etiquetas. `tag_number` es el folio comercial impreso en la etiqueta (paralelo al `asset_number` del propio `Asset`, §13).

Máquina de estados: `ISSUED → PRINTED → ACTIVE`, `→ REPLACED` (desde ACTIVE/PRINTED/ISSUED), `→ VOID` (desde cualquier estado no terminal). `mark_printed()` es idempotente entre ISSUED/PRINTED a propósito — permite reimpresión controlada (§81, permiso `ACTIVOS.etiqueta.reimprimir` ya existe desde ASSET-2) sin modelar un estado separado "REPRINTED".

Nuevos enums: `AssetTagStatus`, `AssetTagType` (QR/BARCODE_128/DATA_MATRIX — §14: "Debe permitir: QR, Code128, DataMatrix futuro"). Excepciones: `AssetTagNotFoundError`, `AssetTagDuplicateError` (ya nombrada en el §108 del prompt maestro), `AssetTagStateInvalidError`. Eventos nuevos: `ASSET_TAG_ISSUED`, `ASSET_TAG_PRINTED`, `ASSET_TAG_ACTIVATED`, `ASSET_TAG_REPLACED`, `ASSET_TAG_VOIDED`. Port: `AssetTagRepositoryPort` (incluye `get_by_qr_token()` — la ruta de resolución pública).

## Explícitamente fuera de alcance

La impresión real (§49, §51: "Toda impresión usa PrintJob", "PDF usa Document Output") no se construye en esta fase — ver `ASSET-15_integraciones.md` para el `PrintJobGatewayPort` que la capa de aplicación (fase posterior) usará para enviar la etiqueta a imprimir sin tocar FPDF directamente (el anti-patrón del legacy `modulos/activos.py`).

## Tests

`tests/unit/assets/test_asset_tag.py` — creación (token QR distinto del id/asset_id, tag_number requerido, tipo por defecto QR), ciclo de vida completo, reimpresión permitida, activar antes de imprimir falla, reemplazar desde ACTIVE, anular desde ISSUED, modificar etiqueta ya terminal falla.

## Siguiente fase

ASSET-14 — QueryServices.
