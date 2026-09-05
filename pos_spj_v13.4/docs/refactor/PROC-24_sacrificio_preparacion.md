# PROC-24 — Preparación de sacrificio: Procesamiento Cárnico

Estado: **DONE** dentro de su propio alcance declarado ("entidades,
contracts, feature flags" — no un motor de ejecución; §37/§50 siguen siendo
*futuro*, esta fase solo deja el terreno preparado)

## Alcance y decisión de arquitectura

El prompt maestro ya había dejado semillas para esto en fases anteriores sin
construir nada encima:

- `ProcessType` (PROC-2) ya tiene los 7 valores `*_FUTURE` de sacrificio
  (`SLAUGHTER_FUTURE`, `BLEEDING_FUTURE`, `SCALDING_FUTURE`,
  `DEFEATHERING_FUTURE`, `EVISCERATION_FUTURE`,
  `CARCASS_CLASSIFICATION_FUTURE`, `POST_MORTEM_PROCESSING_FUTURE`).
- `MeatProcessingPermissions` (PROC-1) ya tiene los 12 permisos
  `SLAUGHTER_*` (`PRODUCCION.sacrificio.*`).
- `MEAT_PROCESSING_NAV` (PROC-4) ya tiene 9 entradas de sidebar bajo
  `feature_flag=SLAUGHTER_FEATURE_FLAG`, ocultas hasta que ese flag esté
  activo.

Lo que faltaba — y es el alcance real de esta fase — es la vocabulario de
dominio (enums), las formas de datos (contracts) y el candado que mantiene
todo esto inerte (feature flag), exactamente como el título de la fase lo
dice. **No** se construyó un motor de ejecución, casos de uso, esquema ni
UI — construir eso ahora sería exactamente el "scaffolding sin consumidor"
que este proyecto ha evitado consistentemente en cada fase (ver, p. ej.,
`events.py`'s propio criterio para no añadir eventos de notificación antes
de PROC-20).

## Precedente: el mismo stub ya existe en Inventory

`backend/domain/inventory/slaughter/` (INV-21) ya modela la mitad de este
futuro flujo — pero desde el lado de **inventario**: `SlaughterOrderContract`/
`CarcassContract`/`SlaughterOutputContract` (§33) y
`SlaughterPlanningService`, que mapea una faena futura sobre los movimientos
y la genealogía que Inventario ya sabe postear, sin persistir nada
(`SLAUGHTER_ENABLED = False` ahí también). Esta fase construye el stub
**complementario**, del lado de Procesamiento: los contratos operativos
(recepción, inspección, clasificación, decomiso, enfriamiento) que
*producirían* la información que el stub de Inventory necesita — nunca
importa el paquete de Inventory directamente (frontera de bounded context,
§64); ambos stubs se relacionarían por id de referencia cuando el módulo
real exista, igual que Procesamiento y Losses se relacionan hoy vía
`LossCaseRequestPort`.

## Nuevo paquete: `backend/domain/meat_processing/slaughter/`

- **`enums.py`**: `AnimalLotStatus`, `SlaughterOrderStatus` (subconjunto
  pequeño de `ProcessingOrderStatus` — un ciclo de vida completo de 15
  estados sería prematuro sin motor de ejecución), `AnteMortemDisposition`,
  `PostMortemDisposition`.
- **`contracts.py`**: 7 `@dataclass(frozen=True, slots=True)` — mismo estilo
  exacto que `backend/domain/inventory/slaughter/contracts.py`:
  `AnimalLotContract`, `SlaughterOrderContract`, `AnteMortemRecordContract`,
  `PostMortemRecordContract`, `CarcassClassificationContract`,
  `CondemnationRecordContract`, `ChillingRecordContract`. Ids UUIDv7,
  cantidades/pesos Decimal-only (float explícitamente rechazado), sin
  persistencia. El campo `grade` de clasificación de canal es texto libre a
  propósito — los estándares de clasificación varían por especie/regulación
  y no le corresponde a este stub inventar una taxonomía regulatoria.
- **`feature_flag.py`**: `SLAUGHTER_ENABLED = False` (constante de módulo,
  no el sistema formal `backend/domain/feature_flags/` — ese es para flags
  configurables en runtime de features *ya construidas*; sacrificio no
  tiene módulo real que alternar todavía, así que el candado a nivel de
  código es lo honesto, igual que el precedente de Inventory) +
  `ensure_slaughter_enabled()`, un guard que levanta
  `MeatProcessingConfigurationError` si algo alguna vez lo invoca mientras
  está deshabilitado — sin consumidor todavía, listo para cuando exista uno.

## Tests

`tests/unit/meat_processing/test_meat_processing_slaughter_contracts.py`
(15 tests): flag deshabilitado por defecto; guard levanta mientras está
deshabilitado; cada contrato valida sus campos requeridos y rechaza float en
cantidades/pesos; estados por defecto correctos (`AnimalLotStatus.RECEIVED`,
`SlaughterOrderStatus.DRAFT`).

## Pendiente

- Todo lo operativo real: recepción física, ejecución de faena, entidades
  persistidas, casos de uso, esquema, UI — condicionado a que el negocio
  decida activar esta línea de producto. Hasta entonces, `SLAUGHTER_ENABLED`
  se queda en `False` y los 12 permisos + 9 entradas de sidebar ya
  existentes permanecen invisibles/inertes.
- Sin puente entre este stub y el de Inventory (`backend/domain/inventory/slaughter/`)
  — se conectarán por id de referencia cuando ambos lados tengan
  implementación real; documentar ese contrato de integración es trabajo de
  esa fase futura, no de esta.
