# SDLC-ASSET-009 — Validaciones de dominio de Activos incompletas o inalcanzables (ubicación raíz, QR, escaneo, seguros, inspecciones, documentos)

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §14, §16, §18, §27, §37, §41, §43, §44, §108 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Defectos de dominio que hoy no tienen impacto porque no hay persistencia, pero que se heredarían al construirla: no se puede crear la ubicación raíz de empresa; la línea de escaneo de inventario no tiene `operation_id` (un escaneo repetido contaría doble); el token público del QR es un UUIDv7 que deja ver la fecha de emisión; un seguro nunca pasa a «por vencer»; el proveedor por garantía nunca se asigna; la inspección no se valida contra su plantilla; los documentos aceptan cualquier tipo MIME y cualquier texto como hash; cinco excepciones declaradas nunca se lanzan.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_location.py:44` — COMPANY exige padre
- `backend/domain/assets/entities/asset_physical_inventory_line.py:24-35` — sin `operation_id`
- `backend/domain/assets/entities/asset_tag.py:56` — `qr_public_token = new_uuid()`
- `backend/domain/assets/entities/asset_insurance_policy.py:61-68` — EXPIRING inalcanzable
- `backend/domain/assets/entities/maintenance_work_order.py:122-124` — WARRANTY_PROVIDER inalcanzable
- `backend/domain/assets/entities/asset_inspection.py:61-72` — sin validar contra plantilla
- `backend/domain/assets/entities/asset_document.py:17,46-54` — 25 MB fijo, MIME/hash solo no vacíos
- `backend/domain/assets/exceptions.py:14,22,43,48,165` — excepciones sin uso; `:166-168` afirma una UNIQUE inexistente

## Impacto
Calidad de datos futura; el token QR afecta privacidad (se puede inferir cuándo se etiquetó).

## Objetivo
- Cada defecto listado corregido con su prueba unitaria.
- Token QR generado con `secrets` y sin relación con la identidad.

## Alcance
- **Incluye:** Entidades listadas.
- **No incluye:** Persistencia.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-7/9/11/13 (septiembre)

## Preguntas abiertas
- ¿Lista de tipos de archivo permitidos para documentos y fotos de activos, y tamaño máximo (hoy 25 MB fijos)?
