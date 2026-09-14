"""Summarize actual pytest artifacts and refresh the measured UI inventory."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
evidence = root / 'docs/refactor/evidence'
audit = json.loads((evidence / 'ui_design_system_audit_20260912.json').read_text())
report_path = root / 'docs/refactor/global_ui_ux_design_system_audit.md'
report = report_path.read_text(encoding='utf-8')
report = report.replace('**2026-09-11**', '**2026-09-12**')
report = report.replace('**593 archivos Python**', f"**{audit['files_scanned']} archivos Python**")
adoption = audit['module_adoption']
totals = Counter()
rows = []
for module, counts in adoption.items():
    totals.update(counts)
    rows.append('| ' + module + ' | ' + ' | '.join(str(counts[key]) for key in (
        'files', 'files_importing_canonical_components', 'files_using_page_layouts', 'files_using_standard_table')) + ' |')
report = report.replace('**419 archivos en 18 módulos**', f"**{totals['files']} archivos en {len(adoption)} módulos**")
report = report.replace('ui_design_system_audit_20260911.json', 'ui_design_system_audit_20260912.json')
table_start = report.index('| assets |')
table_end = report.index('\n\nLos diálogos directos', table_start)
rows.append('| **Total** | ' + ' | '.join(f'**{totals[key]}**' for key in (
    'files', 'files_importing_canonical_components', 'files_using_page_layouts', 'files_using_standard_table')) + ' |')
report = report[:table_start] + '\n'.join(rows) + report[table_end:]

files = (
    'ds-components-shell-final.xml',
    'ds-architecture-appearance-final.xml',
    'design-system-visual-final.xml',
    'design-system-navigation-final.xml',
    'ds-responsive-final.xml',
    'architecture-ui-20260911-results.xml',
)
summaries = {}
passing_cases = set()
global_failures = []
for name in files:
    tree = ET.parse(root / '.test_tmp' / name)
    cases = tree.findall('.//testcase')
    suite = tree.find('.//testsuite')
    info = {key: int(suite.get(key, '0')) for key in ('tests', 'failures', 'errors', 'skipped')}
    info['passed'] = info['tests'] - info['failures'] - info['errors'] - info['skipped']
    info['seconds'] = float(suite.get('time'))
    summaries[name] = info
    for case in cases:
        identity = (case.get('classname'), case.get('name'))
        failed = case.find('failure') is not None or case.find('error') is not None
        if name.startswith('architecture-ui-'):
            if failed:
                global_failures.append({'module': identity[0], 'test': identity[1]})
        elif not failed and case.find('skipped') is None:
            passing_cases.add(identity)

pngs = sorted((evidence / 'design_system_ui').glob('*.png'))
assert len(pngs) == 200, len(pngs)
payload = {
    'date': '2026-09-12',
    'head': subprocess.check_output(['git', '-C', str(root.parent), 'rev-parse', 'HEAD'], text=True).strip(),
    'scope': 'Design system foundation, shell, component validation; global adoption remains incomplete',
    'pytest_runs': summaries,
    'distinct_passing_targeted_tests': len(passing_cases),
    'targeted_test_cases': [{'module': module, 'test': name} for module, name in sorted(passing_cases)],
    'full_architecture_failing_cases': global_failures,
    'full_unit_collection_errors': 13,
    'full_integration_collection_errors': 59,
    'new_visual_violations': 0,
    'existing_visual_occurrences': sum(rule['occurrences'] for rule in audit['rules'].values()),
    'screenshots': [{'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in pngs],
    'limitations': ['Official branding assets absent', 'Production notification source not connected to drawer',
                    'No approved pixel regression baseline', 'Physical touch/scanner/scale acceptance pending',
                    'Full repository test suites are not green'],
}
(evidence / 'design_system_validation_20260912.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
report = report.replace(
    'Antes del cambio: **7 PASSED, 0 FAILED, 0 SKIPPED**. Después: **28 PASSED, 0 FAILED, 0 SKIPPED**, en 80,38 segundos. Son pruebas de arquitectura y del detector; no son 28 capturas visuales ni la suite completa del producto.',
    'El segmento ampliado de arquitectura visual, contraste, composición de ventana, apariencia, Precios y Rendimientos termina con **184 PASSED, 0 FAILED, 0 SKIPPED**. Incluye los 28 guardrails. Los resultados de las suites completas se detallan abajo; no están en verde.')
report = report.replace('Los tests UI del registro', 'Los tests UI del registro')
report += f'''

## Resultado de la fase de infraestructura visual — 12 septiembre 2026

La fase deja componentes canónicos integrados en el shell y evidencia ejecutable.
El cierre global sigue **IN_PROGRESS**: no se atribuye cumplimiento total a los
18 módulos. Referencia de trabajo: rama `claude/erp-financial-bounded-context-uqxz6b`,
HEAD `{payload['head']}` con cambios locales.

### Cambios y defectos corregidos

- Paleta oficial de seis colores, QSS central, Claro/Oscuro y perfiles Compacta,
  Cómoda y Táctil; restauración antes de login y actualización de controles vivos.
- SVG/QIcon real en controles, iconos que siguen el tema, catálogo ampliado y
  galería de componentes. El teclado ya no presenta el icono de archivo por
  confundir la propiedad nativa `QAction.icon` con un identificador semántico.
- Shell con Archivo, Configuración, usuario/sucursal, estado, notificaciones y
  cierre de sesión mediante revocación existente y reconstrucción tras login.
  Configuración reutiliza `PermissionEvaluator`, incluidos comodines, y maneja
  denegaciones del router desde el slot Qt.
- Sidebar global 240/64, ruta persistida y toggle; sidebar de módulo con grupos,
  flyouts y persistencia. Los permisos continúan siendo responsabilidad de la
  composición y del router/backend.
- Layouts de página, viewport y diálogos con límites de monitor. El host usa el
  mínimo de la página activa y evita que una página cacheada o el tamaño sugerido
  de un scroll interno fuerce desplazamiento exterior innecesario.
- Tabla con columnas declarativas, visibilidad/ancho persistentes, ordenación
  Decimal y UUID conservado durante recargas ordenadas. KPIs conservan sus widgets
  al redistribuirse y los combos muestran completa la selección.
- Teclado virtual con validación, selección, mayúsculas, espacio y controles de
  hardware; conserva 52 px de altura también después del polish QSS. Su ancho se
  ajusta a la cuadrícula para mostrar todas las teclas en la matriz solicitada.
- Botones primarios y destructivos presionados en Oscuro corregidos a contraste
  superior a 4.5:1. Las nuevas pruebas reprodujeron los pares anteriores fallidos.
- `YieldMonitoringPage` adopta `StandardPage` sin adelantar consultas.
  `PricingWorkspace` incorpora `PageViewport` y reemplaza marcadores de carga sin
  desplazar los índices de otras páginas. La prueba reproduce abrir secciones
  fuera de orden y regresar a páginas cacheadas.

### Archivos de la fase

La implementación se concentra en `frontend/desktop/themes/`,
`frontend/desktop/components/`, `frontend/desktop/shell/`, `frontend/desktop/auth/`,
`frontend/desktop/app.py` y el contrato/galería de `design_system/`.
Las últimas adiciones de componentes son `selection_controls.py`, `toolbar.py`
y `weight_input.py`; las bases de páginas, ventanas y branding ya se encuentran
en el árbol de trabajo junto con los cambios de sesiones de la fase.
Se modificaron también las dos pantallas de Precios y Rendimientos indicadas.

Pruebas añadidas/ampliadas: `tests/ui/conftest.py`,
`test_theme_density_icons.py`, `test_responsive_components.py`,
`test_design_system_visual_matrix.py`, `test_design_system_navigation_visuals.py`,
contratos del shell/ContentHost, `tests/unit/shell/test_desktop_logout_transition.py`,
`test_authentication_logout.py` y guardrails/contraste de arquitectura.
Guías actualizadas: `design_system/visual_guidelines.md` y `migration_guide.md`.
**Archivos de producto eliminados por esta fase: 0**. Las eliminaciones ajenas
en el árbol de trabajo permanecen identificadas por separado.

### Resultados verificables

| Ejecución | PASSED | FAILED | ERROR | SKIPPED |
|---|---:|---:|---:|---:|
| Componentes, shell, registro y transición logout | 161 | 0 | 0 | 0 |
| Arquitectura visual, contraste, integración y apariencia | 184 | 0 | 0 | 0 |
| Matriz shell/galería + navegación/login/teclado | 40 | 0 | 0 | 0 |
| Revalidación final navegación/login/teclado (incluida en matriz) | 20 | 0 | 0 | 0 |
| Revalidación responsive + revocación de sesión | {summaries['ds-responsive-final.xml']['passed']} | 0 | 0 | 0 |
| Suite completa de arquitectura, ejecución 11 septiembre | 667 | 149 | 1 | 3 |
| Suite completa unit, colección | — | — | 13 | — |
| Suite completa integration, colección | — | — | 59 | — |

Las revalidaciones solapan casos anteriores. Hay **{len(passing_cases)} pruebas distintas
aprobadas** en los segmentos afectados, sin sumarlas dos veces. El
[manifiesto de validación](evidence/design_system_validation_20260912.json)
registra las ejecuciones, nombres de casos, fallos globales y hashes de capturas.

La suite completa de arquitectura contiene referencias a paquetes/rutas
ausentes (`core`, `modulos`, `interfaz`, repositorios retirados), contratos antiguos
y otros incumplimientos de arquitectura. El error de fixture corresponde a
permisos Windows del directorio temporal. Unit e integración se interrumpen en
colección por imports ausentes. No se arreglaron esos problemas alterando tests,
añadiendo shims ni restaurando archivos eliminados por otros cambios.

`compileall -q frontend/desktop` y `git diff --check` terminaron sin errores.
El auditor final mide **0 infracciones visuales nuevas**, **0 huellas obsoletas**
y **159 ocurrencias preexistentes**. Este resultado controla crecimiento de deuda;
no significa que la deuda sea cero.

### Evidencia visual y revisión pendiente

[Abrir el visor de las 200 capturas](evidence/design_system_ui/index.html).
Las 20 combinaciones de resolución/tema/densidad incluyen shell, sidebar global,
drawer, galería desplazada, login, sidebar/grupos de módulo, tabs/dashboard,
formulario con acción fija, Archivo/logout, flyout y teclado. Los formularios
extensos y límites de `StandardDialog` también se comprueban en pruebas Qt.

Se inspeccionaron capturas representativas de Claro/Oscuro y ambos perfiles;
esta revisión detectó los iconos incorrectos, el scroll duplicado y teclas
recortadas que se corrigieron. Las 200 capturas no han recibido aprobación
visual individual. Se cargaron fuentes reales de Windows para evitar aceptar
capturas offscreen con etiquetas vacías.

Checklist de aceptación todavía abierto:

- [ ] Incorporar y revisar los seis recursos oficiales de marca.
- [ ] Conectar `NotificationDrawer` a la fuente productiva de notificaciones.
- [ ] Conectar bloqueo/vencimiento y cambio de sucursal a sus flujos existentes;
      el menú Archivo actual ofrece Cerrar sesión y Salir.
- [ ] Migrar los 35 diálogos directos y revisar los 110 contratos de overflow
      registrados; sustituir los 14 literales cuando funcionen como iconos.
- [ ] Aprobar referencias de píxeles y validar rutas productivas con datos reales,
      permisos, DPI del puesto, lector, báscula y pantalla táctil.
- [ ] Resolver fallos globales de suites y la referencia CI ausente antes de release.

Siguiente etapa: adopción de una ruta productiva completa, con descenso medido
de la deuda y pruebas de sus operaciones, empezando por Configuración. Este
informe no declara finalizada la remediación empresarial completa.
'''
report_path.write_text(report, encoding='utf-8')
print(json.dumps({'distinct_targeted_passes': len(passing_cases), 'screenshots': len(pngs), 'runs': summaries}, indent=2))
