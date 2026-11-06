# SDLC-ASSET-022 — Documentos, fotos, garantías y seguros de activos sin almacenamiento ni avisos de vencimiento

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §40–§43, §107 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-011, SDLC-ASSET-009

## Problema
Documentos, garantías y pólizas existen solo como entidades. No hay almacenamiento de archivos, ni consulta con datos, ni aviso antes de que venza una garantía o un seguro.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/integration_ports.py:60`
- `backend/domain/assets/entities/asset_warranty.py:47-63`
- `backend/application/assets/queries/asset_read_services.py:119-128` — `list_expiring` sin repositorio
- `backend/domain/assets/events.py:73-74` — sin productor

## Impacto
Garantías que vencen sin reclamarse.

## Objetivo
- Almacenamiento de documentos con validación de tipo, tamaño y hash calculado.
- Garantías y seguros persistidos, con aviso configurable antes del vencimiento.
- Pruebas de integración.

## Alcance
- **Incluye:** Documentos, fotos, garantías, seguros, avisos.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-9
- Memoria PROD-21 (copia de imágenes de producto: reutilizar el mecanismo de almacenamiento si aplica)

## Preguntas abiertas
- Ninguna por ahora.
