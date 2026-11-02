# SDLC-UI-031 — Prueba de geometría intermitente: la ventana queda 2 px fuera del área del monitor nuevo

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** destapado en el Build de SDLC-UI-001 (2026-10-31), al comparar la suite completa de `tests/ui` contra la línea base
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-001

## Problema
`test_screen_change_rebinds_available_area_and_disconnects_previous` pasa o falla según la corrida. Cuando falla, tras reducir el área disponible del monitor nuevo la ventana queda en x = -1438 y el área empieza en x = -1440: sobra un borde de 2 px. Puede ser una carrera de eventos en la prueba (`settle`) o un recálculo de `StandardWindow` que no siempre se completa; no se ha determinado.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Las marcadas *medido* salen de comandos ejecutados el 2026-10-31.

- *medido:* `tests/ui/test_standard_window_geometry.py:131` → `assert False`, `QRect(-1440, 0, 800, 600).contains(QRect(-1438, 0, 800, 600))`
- *medido:* 10 corridas aisladas con las guardias de SDLC-UI-001: 5 fallan. 12 corridas con las guardias neutralizadas por un plugin de diagnóstico: 7 fallan. La intermitencia es previa a SDLC-UI-001
- *medido:* en la línea base de SDLC-UI-001 pasó; en la corrida completa del 2026-10-31 falló

## Impacto
Una prueba intermitente en `tests/ui` hace que la suite falle al azar y enseña a ignorar sus fallas. No está marcada `ui_ci`, así que no afecta al job de CI.

## Objetivo
- La prueba da el mismo resultado en 20 corridas seguidas
- Si es defecto de `StandardWindow`, se corrige la ventana, no la prueba

## Alcance
- **Incluye:** `tests/ui/test_standard_window_geometry.py` y `frontend/desktop/components/standard_window.py`.
- **No incluye:** Las 106 fallas de SDLC-UI-002.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`). CLAUDE.md reglas 7 y 13 (UI sin SQL ni reglas de negocio). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
SDLC-UI-001 hizo que `tests/ui` termine completa, y eso dejó ver la intermitencia.

## Preguntas abiertas
- Ninguna por ahora.
