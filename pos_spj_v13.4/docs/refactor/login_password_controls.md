# 13. Controles de usuario/sesión: contraseña de inicio

Validado el 21 de octubre de 2026. Este cambio cubre la petición de mostrar la
contraseña y disponer de teclado virtual en el login; no declara terminado el
resto de funciones del punto 13.

## Comportamiento

- El login inicia con la contraseña oculta y ofrece la casilla accesible
  **Mostrar contraseña**. Cambiarla conserva texto y selección.
- `PasswordInput(keyboard_enabled=True)` incorpora el botón del teclado
  canónico. La opción es explícita para conservar los demás consumidores.
- El modo `password` añade **Símbolos / Letras** al teclado: números, mayúsculas,
  minúsculas, ñ, espacio y los 32 signos ASCII. `&` se dibuja literalmente y se
  inserta una sola vez; Qt no lo interpreta como un atajo del botón.
- El teclado escribe en el campo original, respetando su modo oculto/visible,
  selección, borrado y límites. No crea una segunda copia visible de la clave.
  El envío conserva los espacios y caracteres exactos de la contraseña.
- Un error vuelve a ocultar y limpiar el campo. Al cerrar u ocultar el login
  se desmarca la casilla y se oculta el teclado.
- Se mantienen el tema, densidad y preferencias de teclado de la terminal
  (`icon_only`, `auto_open`, `disabled`); no se sobrescribe la preferencia global.

## Archivos

Modificados:

- `frontend/desktop/auth/login_window.py`: casilla y activación del teclado.
- `frontend/desktop/components/text_inputs.py`: opción explícita en PasswordInput.
- `frontend/desktop/components/virtual_keyboard.py`: modo de contraseña y símbolos.

Añadido: `tests/ui/test_login_password_controls.py` (10 casos).
No se eliminaron archivos ni se cambiaron servicios, reglas de autenticación,
hashes, bloqueo de cuenta, recuperación, esquema o datos.

## Validación

**104 pruebas únicas aprobadas, 1 fallo ajeno al cambio, 0 errores y 0 omitidas.**

| Segmento | Aprobadas | Fallos |
|---|---:|---:|
| Controles nuevos, login con DB real, responsive y controlador de teclado | 57 | 0 |
| Tamaño del teclado, recuperación, asistente inicial y separación UI/datos | 41 | 1 |
| Integración del flujo real de autenticación del shell | 6 | 0 |
| Revisión final de los controles nuevos y capturas (incluidos arriba) | 10 | 0 |

El fallo es `test_owner_account_can_log_in_after_wizard_completes`: importa
`core.services.audit_service`, pero el paquete `core` ya no existe. Falla en ese
import anterior a la autenticación; no se modificó ni se omitió esa prueba.
Los otros siete casos de login con DB real y los seis casos de composición de
autenticación pasan, incluidos credenciales incorrectas y bloqueo de cuenta.

Las pruebas comprueban entrada por botones del teclado, todos los símbolos,
mayúsculas, conservación de espacios, envío único, ocultación al error/cierre,
alternancia mediante teclado físico y geometría en los dos temas y tres
densidades. La integración usa el runner de temporales Qt del workspace para
evitar los problemas de permisos de temporales de Windows ya documentados.

Hay **12 capturas offscreen** (login y teclado de símbolos en cada combinación
de tema/densidad) en [la evidencia](evidence/login_password_controls_20261021/).
Se inspeccionaron visualmente el login Claro/Táctil y el teclado Oscuro/Táctil.
Esto no sustituye una prueba manual en un dispositivo táctil físico.

Desde el paquete interno:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& '..\.venv\Scripts\python.exe' -m pytest tests/ui/test_login_password_controls.py tests/ui/test_login_window.py tests/ui/test_responsive_components.py tests/unit/test_virtual_keyboard_stale_controller.py -q -p no:cacheprovider
```

Para guardar capturas, definir `SPJ_LOGIN_CONTROL_ARTIFACTS` con una carpeta de
destino antes de ejecutar `test_login_password_controls.py`. Los XML, logs y
hashes de los archivos modificados acompañan la evidencia. No se añadieron
exenciones a los guardrails.

Siguiente revisión del punto 13: representación del usuario y estado de sesión,
menú de usuario y acciones de bloqueo/cierre según sus contratos existentes.
