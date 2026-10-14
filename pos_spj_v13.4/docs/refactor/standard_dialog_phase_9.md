# Punto 9 — StandardDialog

**Actualización del 13 de octubre:** la adopción de los diálogos restantes del
shell y las capturas breves está documentada en
[StandardDialog en los módulos del shell](standard_dialog_shell_adoption.md).
Los resultados siguientes conservan la evidencia de la primera entrega.

Implementación y validación: 7–9 de octubre de 2026. Continúa el
[punto 8 — StandardWindow](standard_window_phase_8.md).

La base canónica y su integración en los formularios compartidos de Finanzas
y RR. HH. quedan verificadas: **63 PASSED, 0 FAILED, 0 ERRORS, 0 SKIPPED**
en la ejecución específica del 9 de octubre. Hay **54 capturas** de esa misma
ejecución. La adopción de todos los diálogos de los módulos sigue pendiente;
este informe no declara terminada la estandarización global.

## Comportamiento consolidado

`StandardDialog` centraliza icono oficial, cabecera, contenido desplazable y
botonera fuera del scroll. Usa `BrandAssetProvider`, `PageViewport`, tokens y
QSS global. `FormDialog` conserva el contrato `self.form` para añadir filas.

- `setWindowTitle()` actualiza la cabecera visible; un título vacío la oculta.
  Esto cubre los formularios que cambian de título al entrar en edición.
- El marco completo, incluidas las decoraciones, se limita al área disponible.
  Antes de crear la ventana nativa se usa el monitor del padre; después se sigue
  el del propio diálogo. Se desconectan las señales del monitor anterior.
- Un mínimo solicitado mayor que la pantalla se reduce temporalmente y se
  recupera cuando vuelve a caber. Las coordenadas negativas son válidas.
- Reabrir la misma instancia conserva el tamaño elegido y la captura. Se
  recuperan diálogos completamente fuera del escritorio y se permite atravesar
  el borde de dos monitores conectados durante el traslado.
- Cabecera y botones permanecen accesibles mientras se desplaza el cuerpo.
  La botonera sigue la densidad global y conserva textos y nombres accesibles
  en español. `QDialogButtonBox` mantiene el orden de botones de la plataforma.
- `add_button_box(on_accept=callback)` deja la aceptación en manos del callback:
  este llama a `accept()` después de validar. Sin callback, conserva la
  aceptación directa. No hay una segunda conexión que cierre antes de validar.
- Enter usa la acción predeterminada y Escape llama a `reject()` conforme al
  contrato Qt. `DestructiveConfirmationDialog` mantiene Cancelar como acción
  predeterminada y foco inicial.

`FinanceFormDialog` y `HRFormDialog` ahora heredan `FormDialog`; se retiraron
sus layouts y botoneras duplicados. Esto alcanza **9 formularios de Finanzas y
7 de RR. HH.** por herencia. Los métodos `_build_form`, `_is_valid`, `_error`,
`_accept_if_valid` y `values` conservan sus reglas. La UI sigue capturando datos;
esta fase no cambia operaciones, permisos, SQL, schema ni identidad UUID.

## Protección y resultados

Antes del cambio, las reproducciones mostraron un diálogo perdido fuera del
escritorio, elección del monitor del padre después de mover el diálogo,
restablecimiento de tamaño al reabrir, mínimos incompatibles con pantallas
pequeñas y cabecera desactualizada. La protección inicial de geometría tuvo
5 fallos y 1 aprobado, incluyendo la API nueva de validación aún inexistente.
Las bases de Finanzas/RR. HH. tuvieron 6 aprobados y 12 fallos: conservaron
validación y teclado, pero faltaban la herencia canónica y el overflow.

La ejecución final específica incluye:

| Segmento | Passed | Failed |
|---|---:|---:|
| Geometría, título, callback y teclado de confirmaciones | 11 | 0 |
| Formularios reales de Finanzas/RR. HH., validación, teclado y scroll | 18 | 0 |
| Matriz visual y variantes de confirmación | 34 | 0 |
| **Total del 9 de octubre** | **63** | **0** |

Las ejecuciones ampliadas del 7–8 de octubre quedan preservadas, aunque sus
resultados no equivalen a una revalidación completa del árbol del 9 de octubre:

| Ejecución | Passed | Failed |
|---|---:|---:|
| Regresión de componentes, teclado virtual, POS y compras | 83 | 6 |
| Contratos, recuperación de cuenta, hardware de caja y arquitectura | 50 | 4 |
| Arquitectura de Finanzas/RR. HH. | 21 | 1 |

Al consolidar cada caso por su última ejecución, incluyendo la matriz y los
formularios, hay **199 PASSED distintos, 11 FAILED, 0 ERRORS, 0 SKIPPED**.
No se suman como casos nuevos las repeticiones de geometría ni la revalidación
final. Los XML y el detalle por caso están en
[validation.json](evidence/standard_dialog_phase_9/validation.json).

### Fallos ajenos a esta fase

Los seis fallos de la regresión se reprodujeron cargando únicamente el
`dialogs.py` anterior a esta fase (`cffc218d`) en memoria, conservando las
dependencias actuales. Los mensajes coinciden al normalizar direcciones de
memoria. Las fuentes implicadas también coinciden con esa revisión:

- Dos mocks de cobro no ofrecen `payment_methods()`.
- Un test de caja establece `_sale_id`, pero deja `_sale=None`; `_has_lines()`
  detiene el flujo antes del aviso que espera el test.
- Un test de selector emite una señal con un `QListWidgetItem` ya eliminado.
- Un test todavía busca `modulos/merma.py`, ausente también en la revisión previa.
- Un test espera la propiedad antigua `StatusBadge.status` en lugar de `variant`.

Los otros cinco fallos corresponden a dos pruebas que leen el archivo eliminado
`modulos/configuracion.py`, una que lee `modulos/rrhh.py` y dos guardrails
globales de deuda visual. Las eliminaciones citadas preceden a esta fase.
Los guardrails detectan deuda fuera de la allowlist y entradas obsoletas,
incluida `_directory_base.py` eliminada por el commit de CRM `d9f2bcaf`.

La atribución verificable está en
[comparación de los seis fallos](evidence/standard_dialog_phase_9/dialog-baseline-comparison.json)
y [análisis de los cinco adicionales](evidence/standard_dialog_phase_9/standard-dialog-additional-failures.json).
No se ocultaron estos resultados ni se modificaron sus pruebas para que pasaran.

## Auditoría y adopción

Se retiraron exactamente las dos entradas `noncanonical_dialog` de las bases
Finance/HR de `design_system_debt_baseline.json`. No se amplió la allowlist.
**Cero infracciones nuevas en los tres archivos de producción de esta fase.**

El árbol completo pasó de 132 a 136 hallazgos entre las instantáneas; el cambio
incluye trabajo concurrente de otros módulos. Hay 13 hallazgos fuera de la
allowlist: cuatro ya figuraban en la auditoría inicial y nueve pertenecen a
las nuevas páginas CRM de `d9f2bcaf`. Además de nuestras dos bases, desaparecen
del scan la antigua `_directory_base.py` y dos hallazgos de la galería de
imágenes de Productos por cambios externos a esta fase.

Al cierre, el scan registra 33 ocurrencias `noncanonical_dialog` en 22 archivos.
Ese conteo es de declaraciones/instanciaciones directas detectadas por AST;
no representa el número total de formularios derivados. Su adopción posterior
se mantiene en el punto 23. Los guardrails globales aún requieren atender sus
hallazgos y entradas obsoletas en el alcance correspondiente.

## Evidencia visual y límites

La [galería de 54 capturas](evidence/standard_dialog_phase_9/index.html) contiene:

- 30 capturas: 1280×720, 1366×768, 1440×900, 1600×900 y 1920×1080, cada una
  con Claro/Oscuro y Compacta/Cómoda/Táctil.
- 24 capturas de los formularios reales BankTransferDialog y EmployeeDialog
  ampliados con campos de prueba para forzar scroll, a 640×480, en ambos temas
  y tres densidades, al inicio y al final del desplazamiento.

Se verifican el acceso al último campo, la visibilidad del pie, los mínimos
táctiles, la conservación de datos al cambiar apariencia y el resultado de
clic/Enter/Escape. Se inspeccionaron muestras de Claro/Compacta y Oscuro/Táctil,
incluidas capturas nuevas del 9 de octubre. Son renderizados Qt offscreen con
fuentes reales y áreas de monitor simuladas; no son una comparación automática
contra píxeles previamente aprobados.

Pendiente en equipo real: arrastrar entre monitores con distinto DPI,
desconectar un monitor y comprobar el marco nativo y el teclado virtual mientras
hay captura pendiente. No se probó interacción con escáner, báscula o impresora
físicos. La reapertura conserva geometría dentro de la misma instancia; esta
fase no incorpora persistencia de tamaño entre sesiones de la aplicación.

## Archivos de la fase

Modificados en producción:

- `frontend/desktop/components/dialogs.py` (correcciones integradas en la
  continuación anterior, ya presentes en `29317dca`).
- `frontend/desktop/modules/finance/dialogs/_form_dialog.py`.
- `frontend/desktop/modules/hr/dialogs/_form_dialog.py`.

Pruebas añadidas durante esta fase: `tests/ui/test_standard_dialog_geometry.py`,
`tests/ui/test_standard_dialog_visuals.py` y
`tests/ui/test_finance_hr_standard_dialogs.py`. Esta continuación amplió las
pruebas de teclado y la captura de evidencia de formularios.

Actualizados: `design_system/component_contracts.py`, `migration_guide.md`,
`visual_guidelines.md` y `tests/architecture/design_system_debt_baseline.json`.
Creado este informe y su carpeta de evidencia con XML, logs, auditorías,
comparaciones, hashes y capturas. Archivos eliminados por esta fase: ninguno.
Los cambios concurrentes de CRM, Productos y otros módulos no forman parte de
esta entrega.

Comprobaciones finales: compilación de las fuentes Python del alcance,
`git diff --check`, coincidencia de hashes de fuentes/capturas y consistencia
entre las instantáneas de auditoría y el informe, todas sin errores.

## Reproducción

Desde el paquete interno, usando el entorno de la raíz externa:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:SPJ_DIALOG_VISUAL_ARTIFACTS = 'docs/refactor/evidence/standard_dialog_phase_9/captures'
..\.venv\Scripts\python.exe -m pytest tests/ui/test_standard_dialog_geometry.py tests/ui/test_finance_hr_standard_dialogs.py tests/ui/test_standard_dialog_visuals.py -q -p no:cacheprovider --junitxml=.test_tmp/standard-dialog-final.xml
..\.venv\Scripts\python.exe -m tests.architecture.design_system_audit --json --output .test_tmp/standard-dialog-audit-after.json
```

Siguiente punto del orden solicitado: **10. PageViewport**. Su implementación
actual ya sirve de cuerpo desplazable al diálogo; corresponde revisar y cerrar
su contrato como fase propia.
