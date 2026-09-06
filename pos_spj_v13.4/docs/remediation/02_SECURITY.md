# Fase 2: sin credencial conocida y con identidad de instalación canónica

Fecha de validación: 2026-09-05. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
HEAD de partida: `51112b59c7737480e76baedc7a83fa06c497126b`; cambios locales sin publicar.

## Problema 1 — credencial predeterminada

El esquema born-clean sembraba una cuenta administrativa con contraseña pública y
determinista. Ya no existe: `admin123` solo aparece hoy como entrada de la lista de
contraseñas prohibidas de `backend/security/credentials/password_policy.py` y en las
pruebas que verifican ese rechazo. Una instalación nueva nace sin identidad y queda
bloqueada hasta que `ensure_installation_provisioned` completa el asistente con una
contraseña que introduce la persona usuaria, validada por `PasswordPolicy` y almacenada
con bcrypt.

## Problema 2 — identidad de empresa y estación en almacenamiento paralelo

Hallazgo detectado en esta fase al ejecutar las pruebas que la fase anterior dejó en rojo.

`ProvisionInstallationUseCase` acuñaba `company_id` y `workstation_id` con `new_uuid()` y
guardaba su identidad como filas clave/valor en `configuraciones`
(`company_id`, `empresa_nombre`, `empresa_rfc`, `workstation_nombre`). Ninguno de los dos
identificadores referenciaba un registro: `installation.company_id` apuntaba a un UUID sin
fila, y `installation.workstation_id` a ninguna estación.

En paralelo, el bounded context de Settings ya era dueño de las tablas canónicas
`company_profiles` y `workstations` (migraciones 209 y 210), con entidades de dominio
completas (`CompanyProfile`, `Workstation`) y repositorios que el aprovisionamiento nunca
usaba. Dos domicilios para la misma identidad, exactamente el estado que §49 prohíbe.

Corrección: el caso de uso crea y persiste `CompanyProfile` y `Workstation` a través de
sus repositorios canónicos, dentro del mismo `ProvisioningUnitOfWork`, y la instalación
apunta a esos identificadores reales. Las copias en `configuraciones` se eliminan.
`sucursal_instalacion_id` **se conserva**: `core/services/branch_resolution.py` es un
consumidor real y documentado de esa clave (SET-25), a diferencia de las cuatro retiradas,
que no tenían ningún lector productivo — se verificó antes de eliminarlas.

`InstallationSummaryQueryService` leía la copia `configuraciones.empresa_nombre`. Ahora lee
`company_profiles` a través de `installation.company_id`, de modo que renombrar la empresa
en Configuración se refleja en la pantalla de acceso en vez de dejarla con un nombre
obsoleto de forma permanente.

`workstations.code` es `NOT NULL UNIQUE` y el asistente solo pide un nombre visible, así
que el código se deriva por slug del nombre, con reserva acuñada si el slug quedara vacío.
Divisa, zona horaria e idioma se exponen como parámetros de `execute()` con valores
predeterminados `MXN`/`America/Mexico_City`/`es-MX`, para que el asistente pueda pedirlos
más adelante sin abrir una segunda ruta de aprovisionamiento.

## Pruebas y evidencia

Comandos desde el paquete real `pos_spj_v13.4/`, con `QT_QPA_PLATFORM=offscreen`:

```text
python -m pytest tests/integration/security/ -q -p no:cacheprovider --tb=short
```

Resultado: **60 passed**. Antes de la corrección, `test_provisioning_canonical_profiles.py`
aportaba 5 fallos que demostraban el hallazgo: la empresa y la estación referenciadas no
existían, `configuraciones` duplicaba la identidad, y el resumen de acceso no seguía al
perfil canónico. La prueba de rollback cubre además que un fallo posterior a la creación
de los perfiles no deje empresa ni estación huérfanas, con `isolation_level` normal y en
autocommit.

```text
python -m pytest tests/integration/shell/ -q -p no:cacheprovider --tb=short
```

Resultado: **60 passed**. Las dos fixtures de composición del shell no pasaban
`workstation_name`, obligatorio desde la fase anterior, y erraban en setup (6 errores);
se corrigieron las fixtures, no la validación.

```text
python -m pytest tests/integration/shell/ tests/integration/bootstrap/ \
  tests/ui/test_initial_setup_wizard.py tests/ui/test_login_window.py tests/unit/bootstrap/ \
  -q -p no:cacheprovider --tb=short
```

Resultado previo a la corrección de fixtures: 317 passed, 6 errors.

## Riesgos residuales

El asistente sigue sin pedir divisa, zona horaria ni idioma; se persisten los valores
predeterminados documentados arriba, que ahora quedan en un registro real y editable en
lugar de estar dispersos. No se ejecutó validación visual manual del asistente.

`CompanyProfile` no impone unicidad de empresa: nada impide un segundo perfil si otra ruta
lo creara. El aprovisionamiento es de una sola vez y `InstallationAlreadyProvisionedError`
lo protege, pero la restricción no está en el esquema.

La identidad de empresa/estación queda canónica; el resto del esquema todavía contiene
dinero `REAL` e identidades enteras, y `main.py` sigue construyendo `AppContainer` y
`MainWindow`. Esta fase no los toca.

## Siguiente fase

UUIDv7 y dinero canónico, seguidos del corte de CompositionRoot y shell. La remediación
global permanece abierta.
