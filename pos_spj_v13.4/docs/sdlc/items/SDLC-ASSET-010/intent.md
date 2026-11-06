# SDLC-ASSET-010 — Activos sin persistencia: esquema, repositorios y unidad de trabajo para activo, categoría, ubicación y etiqueta, con folio configurable

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §10–§15, §18, §88 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-002, SDLC-ASSET-004, SDLC-ASSET-008, SDLC-ASSET-009

## Problema
No existe ninguna tabla, repositorio ni unidad de trabajo para el EAM: los 25 puertos de repositorio son Protocols sin implementación, no hay `assets_schema.py` ni `backend/infrastructure/assets/`. Tampoco hay generador del folio operativo (ACT-000001, ACT-QRO-000234) ni restricciones UNIQUE de operación, folio, serie o etiqueta. Es la base de todo lo demás.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/repository_ports.py:44-247` — 25 Protocols sin implementación (barrido A, B, C)
- No existen `backend/infrastructure/db/schema/assets_schema.py`, `backend/infrastructure/db/repositories/assets/`, `backend/infrastructure/assets/`
- `tests/architecture/test_assets_use_uuidv7.py:34-35` — skip «assets_schema.py no existe aún» (*verificado directamente*)
- `backend/domain/assets/entities/asset.py:82-83` — folio solo «no vacío»

## Impacto
Sin esto no se puede registrar ni un equipo. Es la primera pieza del camino crítico del módulo.

## Objetivo
- Esquema born-clean UUIDv7/Decimal (TEXT) para activo, categoría (con seed configurable), ubicación jerárquica y etiqueta, con migración registrada.
- UNIQUE(operation_id), UNIQUE(asset_number), UNIQUE(tag_number) y UNIQUE(serial_number) cuando aplique.
- Generador de folio configurable por formato y, si se decide, por sucursal.
- Repositorios SQLite y unidad de trabajo con pruebas de integración sobre SQLite real.
- La guardia de UUIDv7 deja de omitirse.

## Alcance
- **Incluye:** Esquema, migración, repositorios, UoW, folio, pruebas de integración.
- **No incluye:** Casos de uso (SDLC-ASSET-011) y lectura en UI (SDLC-ASSET-012). Mantenimiento, custodia, etc. (sus propios ítems agregan sus tablas).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- ASSET-3 (dominio base)
- Memoria: `supplier_schema.py` no tiene mecanismo de ALTER — toda columna nueva necesita dos patas

## Preguntas abiertas
- Formato del folio: ¿global (ACT-000001) o por sucursal (ACT-QRO-000234)? Por sucursal, ¿Quién lo configura?  gerente 
