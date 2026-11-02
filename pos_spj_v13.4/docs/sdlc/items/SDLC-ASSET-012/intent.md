# SDLC-ASSET-012 — Activos abre vacío: el shell lo compone con `query_services={}` y faltan 11 de 17 servicios de consulta

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §8, §9, §63, §93, §94 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-010, SDLC-ASSET-007, SDLC-ASSET-001

## Problema
El módulo es visible en el menú pero se arma sin ningún servicio de consulta, así que tablero, directorio, detalle, tablero de OT y agenda siempre salen vacíos. Existen 6 de los 17 servicios de consulta pedidos, todos sobre puertos sin implementación. El directorio solo filtra por texto y estado y muestra 5 columnas; el detalle es un panel único sin pestañas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/assets/shell_registration.py:81-87` — `query_services={}` (*verificado directamente*)
- `backend/application/assets/queries/asset_read_services.py:46-140` — 6 servicios
- `frontend/desktop/modules/assets/assets_workspace.py:120-138` — 5 páginas, 31 marcadores
- `frontend/desktop/modules/assets/pages/assets_directory_page.py:68-81` — filtros y columnas
- `frontend/desktop/modules/assets/pages/asset_detail_page.py:37-52` — panel único

## Impacto
Usuario que entra a Activos no ve nada, aunque Finanzas tenga activos registrados.

## Objetivo
- La composición real del shell inyecta servicios de consulta sobre los repositorios de SDLC-ASSET-010.
- Directorio con los filtros y columnas de §93 que tengan dato; detalle con pestañas con `route_id` para las secciones que ya existan.
- Prueba de composición real (no presentador falso) que abre Activos con datos en SQLite.

## Alcance
- **Incluye:** Composición, servicios de consulta del registro, directorio y detalle.
- **No incluye:** Páginas de mantenimiento, custodia, etc. (sus ítems).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- SDLC-ASSET-001 (decisión de ocultar el módulo hasta construirlo, intent aprobado)
- Memoria shell cutover: leer `desktop_shell_window_composition.py`, no los docstrings

## Preguntas abiertas
- Ninguna por ahora.
