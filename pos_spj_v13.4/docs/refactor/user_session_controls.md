# 13. Controles de usuario/sesión: menú del shell

Continuación del 21 de octubre de 2026, posterior al
[login con contraseña visible y teclado virtual](login_password_controls.md).

## Comportamiento incorporado

- El bloque superior con nombre, sucursal y estado abre el menú de usuario.
  Usa el botón canónico, mantiene un nombre accesible completo y se puede
  abrir con Espacio y cerrar con Escape.
- **Mi perfil** abre un `StandardDialog` de consulta: usuario, roles, sucursal
  y estado actual. Los datos proceden del `ApplicationContext` vigente al
  abrirlo. Nombres de usuario y sucursal se representan como texto plano.
- **Cerrar sesión** comparte la misma `QAction` con el menú Archivo. Conserva
  la confirmación con respuesta negativa por defecto y el flujo existente de
  revocación/reautenticación. No incorpora una segunda ruta de cierre.
- Al navegar, el estado superior refleja el modo de la ruta: conectado,
  sin conexión o conexión limitada. Los avisos visuales de bloqueo/vencimiento
  conservan prioridad ante una actualización de conectividad de la misma
  sesión; se reinician al recibir otra sesión.

## Archivos

Modificados:

- `frontend/desktop/shell/application_shell/top_bar.py`: menú, botón adaptable
  y separación entre conectividad y aviso de sesión.
- `frontend/desktop/shell/application_shell/application_window.py`: apertura
  del perfil y actualización de conectividad al navegar.
- `frontend/desktop/design_system/migration_guide.md`: contrato de consumo.

Nuevos:

- `frontend/desktop/shell/application_shell/user_profile_dialog.py`.
- `tests/ui/shell/test_user_session_controls.py`: 13 casos.
- Este informe y `docs/refactor/evidence/user_session_controls_20261021/`.

Sin archivos eliminados, cambios de esquema, SQL nuevo, reglas de negocio,
lecturas de credenciales ni nuevas dependencias.

## Validación

**90 pruebas aprobadas, 1 fallo preexistente, 0 errores y 0 omitidas.**

| Segmento | Aprobadas | Fallos |
|---|---:|---:|
| Controles, navegación, barras y cierre de sesión | 49 | 0 |
| Integración de composición, separación UI/datos y diálogos canónicos | 41 | 1 |

El fallo es `test_native_input_dialogs_use_the_canonical_capture_components`:
detecta `QInputDialog` en Compras, `enterprise_pages.py:373` y
`returns_page.py:151`. Ambas llamadas existen en `HEAD` y esos archivos no
forman parte de este cambio. El perfil nuevo cumple el contrato de propiedad
de `StandardDialog`. No se declara verde la suite global.

Se ejecutaron pruebas de interacción, navegación, confirmación del cierre,
transición de autenticación y geometría con ambos temas y las tres densidades.
Los resultados finales y hashes se conservan en `validation.json`, junto con
los XML y logs de ejecución, en la carpeta de evidencia.

Hay 12 capturas offscreen: shell y perfil por combinación. Se inspeccionaron
Claro/Táctil y Oscuro/Táctil. La matriz detectó un recorte inicial del botón al
alojar etiquetas; se corrigió su cálculo de tamaño y las seis combinaciones
pasaron. No se modificaron allowlists ni se omitieron pruebas para ocultarlo.

Reproducción desde el paquete interno:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& '..\.venv\Scripts\python.exe' -m pytest tests/ui/shell/test_user_session_controls.py tests/ui/shell/test_top_bar.py tests/ui/shell/test_application_window.py tests/ui/shell/test_status_bar.py tests/ui/shell/test_shell_ui_contracts.py tests/unit/shell/test_authentication_logout.py tests/unit/shell/test_desktop_logout_transition.py -q -p no:cacheprovider
```

Para capturas, definir `SPJ_SESSION_CONTROL_ARTIFACTS` antes de ejecutar la
matriz. Pendiente de verificación manual en Windows con pantalla táctil:
abrir el menú tocando el nombre/estado, abrir/cerrar el perfil, cancelar el
cierre conservando la pantalla y confirmarlo para regresar al login.

## Pendientes del punto 13

Este ciclo completa la presentación y el menú de las acciones conectadas;
no declara terminado todo el punto 13.

- **Bloquear/desbloquear:** falta un contrato de reautenticación de la sesión
  actual que proteja las vistas abiertas. `set_session_state("locked")`
  continúa siendo presentación, no una barrera de seguridad.
- **Cambiar sucursal:** existe `ApplicationContextService.change_branch`, pero
  falta conectarlo al shell con verificación real de operaciones pendientes,
  permisos, selección de sucursal e invalidación de servicios/vistas. No se
  añadió una acción que altere únicamente las etiquetas del contexto.
- **Vencimiento:** el aviso visual necesita conectarse al ciclo de vida del
  `SessionManager`; no se introdujo un temporizador de vencimiento ficticio.

Siguiente ciclo: proteger con pruebas el bloqueo y la reautenticación antes
de publicar esa acción en el menú.
