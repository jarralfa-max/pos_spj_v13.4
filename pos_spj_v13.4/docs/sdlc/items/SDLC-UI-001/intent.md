# SDLC-UI-001 — La suite tests/ui no termina (una prueba tumba el proceso) y los jobs ventas/ui/api de CI llaman un script inexistente

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §43, §45.25 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-30, Alfred)
- **Depende de:** —

## Problema
Correr `tests/ui` completo nunca llega al resumen: una prueba del diálogo de cobro mata el proceso de Python sin salida, y las 487 pruebas que vienen después nunca se ejecutan. En CI, los jobs ventas, ui y api llaman `./scripts/ci/run_domain_tests.sh`, que no existe, y de `tests/ui` solo se corre `test_purchasing_visual_closure.py`. Nadie puede afirmar hoy que la UI pasa sus pruebas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- *medido:* `QT_QPA_PLATFORM=offscreen python -m pytest tests/ui -q` colecta 1483 pruebas, ejecuta 996 y termina con código 127 sin resumen; corrido dos veces con el mismo resultado
- *medido:* `tests/ui/test_operations_standard_dialogs.py::test_payment_retry_keeps_recorded_lines_and_accepts_once` corrida sola: código 127, 0 bytes de salida
- `../.github/workflows/ci-segmented.yml:125,146,167` → `./scripts/ci/run_domain_tests.sh` (no existe `scripts/ci/` en la raíz ni en `pos_spj_v13.4/`)
- `../.github/workflows/ci-segmented.yml:48-53`: único paso de `tests/ui` en CI
- Causa del cierre: **no verificado**. Hipótesis: un diálogo modal real o un `QApplication` creado dentro de la prueba (patrón conocido del repo que mata pytest en silencio)

## Impacto
Afecta a todo cambio de UI y del POS: las pruebas de cobro, diálogos y layouts dejan de correr en silencio. Los jobs de CI de ventas, UI y API fallan sin probar nada.

## Objetivo
- `python -m pytest tests/ui -q` llega al resumen en Windows y en CI
- La prueba que tumba el proceso falla o pasa como prueba normal, sin derribar la corrida
- Los jobs ventas/ui/api de CI ejecutan un comando existente o se retiran con decisión registrada
- `tests/ui` (o un subconjunto acordado) corre en CI

## Alcance
- **Incluye:** Diagnóstico del cierre, corrección de la prueba o del fixture, comando de los jobs de CI.
- **No incluye:** Las 96 fallas de aserción (SDLC-UI-002).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
Triage 2026-10-28: SDLC-CORE-007 (el segmento de integración no colecta) es el mismo patrón en otro segmento. Memoria del repo: una QApplication creada dentro de una prueba mata pytest sin aviso.

## Preguntas abiertas
- ¿`tests/ui` completo debe correr en CI (tarda varios minutos) o solo un subconjunto marcado? subconjunto
- ¿Los jobs ventas/ui/api se restauran con un script nuevo o se eliminan del workflow? eliminan
