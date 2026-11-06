# SDLC-ASSET-027 — Etiquetas, QR y reporte PDF de activos se perdieron con el legacy

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §4, §14, §49–§51 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-010, SDLC-ASSET-009

## Problema
El legacy imprimía etiquetas y exportaba un reporte PDF de activos. Se borró y no hay reemplazo: solo un puerto de impresión sin implementación y la ruta «Etiquetas y QR» en construcción.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/integration_ports.py:69-75`
- `backend/domain/assets/entities/asset_tag.py:29-91`
- `frontend/desktop/modules/assets/assets_routes.py` — `assets.tags` sin página

## Impacto
Funcionalidad operativa perdida (CLAUDE.md, prioridad 0).

## Objetivo
- Etiquetas con logo, folio, nombre, sucursal, ubicación, QR con token público y Code128, por Document Output → PrintJob (PDF y térmica), sin exponer el UUID.
- Reimpresión controlada y reemplazo de etiqueta.
- Reporte PDF de activos por Document Output.
- Pruebas.

## Alcance
- **Incluye:** Etiquetas, QR, Code128, reporte PDF.
- **No incluye:** DataMatrix (futuro).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria LOG-INT: etiquetas QR de contenedores en PDF/térmica, QR validado contra firma — reutilizar
- Memoria TICKET-AUD (Document Output)

## Preguntas abiertas
- Ninguna por ahora.
