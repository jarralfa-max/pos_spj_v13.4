# CI Hardening por dominios (ventas/UI/API)

Este documento define la estrategia para reducir falsos negativos de infraestructura y dar señal confiable por dominio.

## Objetivo

- Separar pruebas por dominio funcional.
- Fijar entorno mínimo por job (Python, Qt/headless, librerías de sistema).
- Evitar que una dependencia de UI/API rompa la validación de ventas.

## Segmentación propuesta

1. **Job ventas**
   - Ejecuta únicamente pruebas del flujo de ventas refactorizado.
   - Incluye no-duplicidad, fidelidad, normalización de pago, guardrail legacy y MP pendiente/confirmación.

2. **Job UI**
   - Ejecuta pruebas de UI del flujo de ventas en modo headless.
   - Requiere `QT_QPA_PLATFORM=offscreen` y librerías GL/X11 mínimas.

3. **Job API**
   - Ejecuta pruebas de API separadas del stack UI.
   - Se instala explícitamente `fastapi/starlette/httpx/anyio`.
   - Se excluyen tests que dependen de GL/Qt cuando no aportan a API.

## Entorno recomendado

- Python: 3.11 para CI estable (evita incompatibilidades observadas en 3.14 con `starlette.testclient`).
- Variables:
  - `PYTHONUNBUFFERED=1`
  - `QT_QPA_PLATFORM=offscreen`
- Paquetes de sistema UI:
  - `libgl1`, `libegl1`, `libxkbcommon-x11-0`

## Workflow

Se añadió `.github/workflows/ci-segmented.yml` con 3 jobs (`ventas`, `ui`, `api`) para que cada dominio falle de forma aislada y accionable.
Los tres jobs usan el mismo lanzador `scripts/ci/run_domain_tests.sh` para evitar divergencia de comandos entre dominios.
Además, los jobs comparten base de entorno consistente:
- Python 3.11
- `QT_QPA_PLATFORM=offscreen`
- dependencias de sistema GL/X11
- dependencias Python comunes (`pytest`, `PyQt5`, `fastapi`, `starlette`, `httpx`, `anyio`)

## Criterio de éxito

- Un PR de ventas debe poder pasar `ventas` aunque fallen pruebas API/UI no relacionadas.
- Las fallas de UI/API deben reportarse en sus propios jobs sin bloquear diagnóstico del dominio ventas.
