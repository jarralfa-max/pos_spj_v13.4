# Manual de instalación, actualización y reversión por sucursal

Para: encargado de sistemas que instala SPJ ERP POS en las cajas y oficinas.
Contrato técnico: [`docs/architecture/INSTALLER_AND_UPDATER.md`](../architecture/INSTALLER_AND_UPDATER.md).

## 0. Antes de empezar

* Use sólo el instalador oficial `SPJ-Setup-<versión>-x64.exe` y compruebe su hash con
  el archivo `.sha256` que lo acompaña: `Get-FileHash .\SPJ-Setup-13.5.0-x64.exe -Algorithm SHA256`.
* En producción el instalador debe estar firmado: clic derecho → Propiedades → Firmas
  digitales → editor «SPJ». Si no tiene firma, es una compilación de prueba: no la instale en una caja.
* Instalar y actualizar piden autorización de administrador de Windows (UAC).
* Windows 10/11 de 64 bits. No hace falta Python ni Git.

## 1. Instalación nueva

1. Ejecute el instalador como el usuario que administra el equipo.
2. **Tipo de instalación**
   * *POS esencial*: venta, caja, productos, inventario, precios, clientes y fidelidad.
   * *ERP completo*: todos los módulos.
   * *Personalizado*: elija módulos; los que dependen de otro lo agregan solos
     (RR. HH. y Activos agregan Finanzas). El núcleo no se puede quitar.
   El perfil oculta y bloquea módulos; no ahorra espacio en disco (todos los archivos se instalan).
3. **Ubicación de los datos**: en cajas compartidas elija «Todos los usuarios»
   (`C:\ProgramData\SPJ\SPJ ERP POS`). «Sólo mi usuario» usa `%LOCALAPPDATA%\SPJ\SPJ ERP POS`.
   Esta elección no se cambia en actualizaciones.
4. **Base de datos anterior**: déjelo vacío en una caja nueva (vea §3 si la caja ya usaba SPJ).
5. **Servicio WhatsApp local**: no lo marque, salvo indicación expresa. En producción se usa
   el servicio remoto. Sólo se ofrece con datos para todos los usuarios.
6. Al abrir SPJ por primera vez aparece el asistente: empresa, sucursal, estación y propietario.

Instalación desatendida (despliegue masivo):

```powershell
.\SPJ-Setup-13.5.0-x64.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DATASCOPE=machine `
  /TYPE=pos_essential /CHANNEL=stable /LOG=C:\Temp\spj-install.log
# Personalizado:  /TYPE=custom /COMPONENTS="nucleo,modulos\fidelidad,modulos\purchasing"
# Base anterior:  /LEGACYDB="D:\SPJ\pos_spj_v13.4\data\spj_pos_database.db"
```

Comprobación sin abrir ventanas:

```powershell
& "C:\Program Files\SPJ\SPJ ERP POS\SPJ.exe" --self-test --json --report C:\Temp\spj-selftest.json
Get-Content C:\Temp\spj-selftest.json     # "ok": true y la versión esperada
```

## 2. Dónde está cada cosa

| Qué | Dónde | ¿Lo toca el instalador? |
| --- | --- | --- |
| Programa | `C:\Program Files\SPJ\SPJ ERP POS` | Sí (lo reemplaza al actualizar) |
| Base de datos | `<datos>\db\spj_pos_database.db` | **Nunca** |
| Respaldos | `<datos>\backups` (`pre-update-…`, `pre-relocation-…`, con `.json`) | Nunca |
| Registros | `<datos>\logs` (`spj_pos.log`, `updater.log`, `instalador-….log`) | Nunca |
| Imágenes y medios | `<datos>\imagenes_productos`, `<datos>\media` | Nunca |
| WhatsApp local | `<datos>\whatsapp\whatsapp.env` y `conversations.db` | Nunca |
| Secretos | Administrador de credenciales de Windows (o `<datos>\secrets`) | Nunca |
| Instaladores para revertir | `C:\ProgramData\SPJ\Installers\SPJ ERP POS` | Sólo el instalador |

`<datos>` = `C:\ProgramData\SPJ\SPJ ERP POS` o `%LOCALAPPDATA%\SPJ\SPJ ERP POS`.
Configuración → Acerca de y actualizaciones muestra las rutas reales de esa estación.

## 3. Caja que ya usaba SPJ desde una carpeta (base anterior)

1. Cierre SPJ en esa caja. Haga una copia manual de la carpeta `data` anterior (por si acaso).
2. Instale e indique en «Base de datos anterior» el archivo `...\data\spj_pos_database.db`.
3. Al abrir SPJ, la base se traslada UNA vez: respaldo verificado en `<datos>\backups`
   (`…pre-relocation…`), copia verificada (integridad, mismas filas por tabla, mismo esquema),
   y el archivo original queda renombrado `spj_pos_database.db.relocated-<fecha>` con un `LEEME`.
4. Verifique ventas del día, usuarios y catálogo. Borre el archivo `.relocated-…` sólo semanas
   después, cuando todo opere normalmente.

Si SPJ dice «la base anterior está en uso», cierre el programa que la tenga abierta (la versión
vieja de SPJ, un visor de SQLite) y vuelva a abrir SPJ.

### «Dos bases de datos» (arranque detenido)

SPJ encontró la base de esta instalación Y una base anterior sin trasladar. No elige sola.
1. Decida cuál es la buena (fecha de la última venta).
2. Si la buena es la anterior: cierre SPJ, renombre `<datos>\db\spj_pos_database.db` a
   `spj_pos_database.db.descartada-<fecha>` y abra SPJ (se trasladará la anterior).
3. Si la buena es la nueva: renombre la anterior a `spj_pos_database.db.archivada-<fecha>`.

### «La base fue reubicada y ya no está»

Alguien borró o movió la base después del traslado. SPJ no crea una vacía. Restaure el respaldo
indicado en `<datos>\db\relocation.json` (§6).

## 4. Actualizar

### Desde la aplicación (en línea u offline)

Configuración → **Acerca de y actualizaciones** (permiso `CONFIGURACION.actualizacion.ver`
para ver; `…administrar` para descargar/instalar; `…canal` para canal y ventana).

1. «Buscar actualizaciones». Sólo se aceptan versiones firmadas con la clave de SPJ, del canal y
   arquitectura de la estación, más nuevas que la instalada y compatibles con el esquema de la base.
2. «Descargar» (verifica tamaño y SHA-256) o «Importar paquete offline…» (memoria USB con
   `manifest.json` + instalador; mismas verificaciones).
3. «Instalar ahora»: SPJ se niega si hay una venta en captura, un cobro pendiente o un corte de
   caja en curso. O «Instalar en la ventana»: se instala sola dentro del horario de mantenimiento
   cuando la caja esté libre. Nada interrumpe una venta, aunque la versión sea obligatoria.
4. SPJ se cierra, aparece «Actualizando SPJ», Windows pide autorización, se respalda la base,
   se instala, se prueba el arranque y SPJ se vuelve a abrir mostrando el resultado.

### Despliegue escalonado por sucursal

* Marque 1–2 cajas como canal **Piloto** (Acerca de → Canal). Reciben las versiones antes.
* El manifiesto puede limitar el despliegue por porcentaje de estaciones, por sucursal o por
  estación concreta; las estaciones fuera del despliegue ven «aún no corresponde».
* La tabla `software_station_settings` (y el historial de cada estación) dice qué versión y
  canal tiene cada caja; `software_update_events` registra cada búsqueda, descarga, instalación
  y reversión.

### Sin la aplicación (actualización manual)

Cierre SPJ en la caja y ejecute el nuevo instalador: conserva perfil, ubicación de datos y
componentes. Al abrir, SPJ aplica las migraciones. Tome antes un respaldo manual (§6) — la
actualización desde la aplicación lo hace sola, la manual no.

## 5. Si algo falla

| Lo que ve | Qué pasó | Qué hacer |
| --- | --- | --- |
| «Actualización revertida» | Falló la instalación o la prueba de arranque; se restauró la base (si hacía falta) y se reinstaló la versión anterior. | Nada urgente. Envíe `<datos>\logs\updater.log` y `instalador-*.log`. |
| «Actualización no aplicada» | No se llegó a instalar (UAC rechazado, SPJ abierto, paquete alterado, respaldo imposible). | Corrija la causa indicada y reintente. Los datos no cambiaron. |
| «Se está instalando…» al abrir | El actualizador sigue trabajando. | Espere; SPJ se abrirá solo. |
| Ventana «Recuperación» | La reversión automática no terminó (o el equipo se apagó a mitad). | Pulse «Recuperar»: restaura la base previa a la actualización y reinstala la versión anterior. Si vuelve a fallar, §6. |
| «La base fue actualizada por una versión más nueva» | Se instaló un programa anterior sobre una base ya migrada. | Instale la versión nueva, o restaure el respaldo `pre-update-…` (§6) y luego la versión anterior. |

## 6. Restaurar un respaldo a mano

1. Cierre SPJ (y el servicio WhatsApp local: `spj_whatsapp.exe stop` como administrador).
2. En `<datos>\backups` elija el archivo (`…pre-update-<versión>-<fecha>.db`); su `.json` dice
   versión, esquema, filas por tabla y hash.
3. Renombre la base actual a `spj_pos_database.db.antes-de-restaurar-<fecha>` y borre (o mueva)
   sus `-wal` y `-shm` si existen.
4. Copie el respaldo a `<datos>\db\spj_pos_database.db`.
5. Si el respaldo es de una versión anterior, reinstale esa versión con
   «Reparar SPJ ERP POS» del menú Inicio sólo si coincide; si no, use el instalador de esa
   versión. Abra SPJ y verifique.

## 7. Reparar y desinstalar

* **Reparar**: menú Inicio → SPJ → «Reparar SPJ ERP POS» (reinstala la versión actual sin tocar datos).
* **Desinstalar**: «Aplicaciones instaladas» de Windows. Los datos se conservan siempre; bórrelos
  a mano sólo si la caja se da de baja y ya tiene respaldo.

## 8. Servicio WhatsApp local (opcional)

* Componente del instalador; se registra como servicio de Windows `SPJWhatsApp`.
* Configuración y secretos en `<datos>\whatsapp\whatsapp.env` (no en la carpeta del programa).
  Por defecto escucha sólo en `127.0.0.1:8000`; exponerlo requiere proxy o túnel y `WA_BIND_HOST`.
* Diagnóstico: `"C:\Program Files\SPJ\SPJ ERP POS\spj_whatsapp.exe" run` (en primer plano).
* `start_all.bat` es una herramienta de desarrollo: no se usa en cajas.
