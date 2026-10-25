# Fallo de acceso SQLite — 2026-10-21

## Evidencia

- El arranque se detuvo en `database_integrity` con `disk I/O error`.
- La reproducción de lectura devolvió código extendido 1546,
  `SQLITE_IOERR_TRUNCATE`.
- Windows Restart Manager identificó `python.exe`, PID 15480, como proceso
  que mantiene abiertos archivos de esta base. No fue posible obtener su
  comando ni identificar su tarea; no se terminó automáticamente.
- El bloqueo canónico `InstanceLock` estaba disponible. Bajo ese bloqueo se
  copiaron `.db`, `-wal` y `-shm`, verificando SHA-256 de origen y copia.
- La copia completa devuelve `PRAGMA integrity_check = ok` y cero filas en
  `PRAGMA foreign_key_check`. La campaña «mon» está ACTIVE y termina el
  2026-10-28T23:29:24; se conserva la configuración posterior del usuario.
- La secuencia canónica de arranque sobre una copia de trabajo termina
  con `success=True`, estado RUNNING e instalación PROVISIONED. Reporta una
  advertencia de cobertura de tablas (`detalle_ventas`, `empleados`) que no
  corresponde al error de acceso investigado.

No hay evidencia de corrupción en la copia verificada. El error de acceso
del original y el proceso que mantiene sus archivos abiertos son compatibles
con un bloqueo de archivos; confirmar causalidad requiere liberar el proceso
y repetir la comprobación sobre el original.

Según [SQLite](https://www.sqlite.org/rescode.html#ioerr_truncate), el código
1546 indica un fallo del sistema de archivos al cambiar el tamaño de un
archivo. No equivale por sí mismo a corrupción de registros.

## Archivos de respaldo y comprobación

Directorio: `docs/refactor/evidence/database_io_20261021/`.

- `original/`: copia de los tres archivos, sin abrir con SQLite.
- `manifest.json`: tamaños y hashes de esa copia.
- `verification/`: copia de trabajo usada para integridad y arranque.
- `copy_bootstrap.txt`: resultado de los pasos del arranque.

Durante el diagnóstico no se sustituyó ni eliminó la base original, el WAL o el SHM.
No se ejecutaron migraciones sobre el original ni se cambiaron reglas de negocio. La adquisición
del bloqueo canónico actualiza únicamente el PID informativo de `.db.lock`.

## Resolución autorizada

El usuario autorizó explícitamente cerrar el proceso 15480. Se volvió a verificar
mediante Restart Manager que seguía manteniendo abiertos los archivos de esta
base. Windows denegó el cierre sin privilegios administrativos; se solicitó
elevación UAC y el ayudante comprobó nombre y fecha de creación del proceso para
evitar cerrar otro proceso si el PID se reutilizaba. Se cerró únicamente el PID
autorizado y se esperó su salida.

Después del cierre, bajo el bloqueo canónico, la base original devolvió:

- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: cero violaciones.
- Secuencia canónica de arranque: `success=True`, estado `RUNNING`.
- Campaña «mon»: ACTIVE, con término 2026-10-28T23:29:24.

El error de acceso desapareció al liberar el proceso. No fue necesario restaurar
un respaldo ni eliminar manualmente archivos de SQLite. Se ejecutó la secuencia
canónica de arranque sobre el original, incluido su paso de migraciones; conserva
la advertencia de cobertura de tablas descrita arriba. No se abrió la interfaz
gráfica ni se modificó código de aplicación.

Resultados: `process_close_result.txt` y `original_after_process_close.json`
en el directorio de evidencia. El respaldo previo permanece en `original/`.

## Recurrencia y corrección del cierre

El error se repitió con código 1546. Restart Manager identificó esta vez el
PID 17568. Una consulta administrativa confirmó que ejecutaba `main.py` usando
el entorno virtual de este proyecto; su padre 12144 ya no existía. Se copió de
nuevo DB + WAL + SHM bajo el bloqueo canónico y se comprobaron hashes e integridad:
`ok`, cero violaciones de claves foráneas. Ese respaldo es independiente del
primer incidente y conserva los cambios posteriores del usuario.

Se cerró únicamente esa instancia huérfana de SPJ, comprobando nombre, fecha de
creación, comando y ausencia del padre. La base original volvió a pasar integridad
y la secuencia de arranque (`success=True`, `RUNNING`). No se restauró una base
anterior ni se eliminaron manualmente archivos SQLite.

La revisión encontró omisiones reales en el cierre:

- La salida normal liberaba el candado sin cerrar explícitamente la conexión
  principal ni la conexión del pool del hilo.
- Cancelar el login o fallar después de abrir SQLite evitaba esa limpieza.
- El cierre de la ventana principal sin coordinador no detenía los servicios
  vinculados ni invocaba el cierre del monitor del cliente.

`frontend/desktop/app.py` ahora mantiene la propiedad de los recursos en un
`try/finally`: detiene servicios, cierra ambas conexiones y libera el candado al
final. El cierre para actualizar usa esa misma ruta; un fallo al lanzar el
actualizador mantiene la sesión abierta y reinicia los servicios.
`ApplicationWindow.closeEvent` detiene servicios cuando no hay coordinador y
cierra sus ventanas secundarias, incluido el reproductor del cliente.

Seis regresiones fallaron antes de corregir esas omisiones. La suite final
obtuvo **55 passed**, incluyendo cancelación, salida normal, excepciones, fallo
de servicios, cierre del monitor, handoff de actualización, logout y controles
arquitectónicos. No se cambió lógica de ventas ni el contenido de campañas.

Evidencia: `evidence/database_io_20261021/recurrence/`, con `original/`,
`manifest.json`, `original_verified.json` y `shutdown_final.txt`.
La liberación del proceso resuelve el incidente observado; las pruebas protegen
las rutas de cierre corregidas. No se afirma haber reproducido cómo se perdió
el padre de la instancia anterior ni se garantiza limpieza ante una terminación
forzada del proceso desde el sistema operativo o el IDE.
