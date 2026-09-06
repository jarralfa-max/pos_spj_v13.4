# Fase 4a: guardrules que fallaban por su propia prosa, y legacy ya borrado

Fecha de validación: 2026-09-05. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
Parte de: `51112b59` + `62ad66c5` + `ecc95744`.

## Corrección a un juicio anterior

`01_CI.md` afirma que los 47 fallos restantes son "deuda arquitectónica real y ahora
visible, no ruido". Al trabajarlos uno por uno resultó ser cierto solo en parte:
**al menos tres eran falsos positivos de los propios guardrules**, no infracciones. La
afirmación se corrige aquí en lugar de dejarla en pie.

Un guardrail que falla por un motivo equivocado es tan dañino como uno que no se ejecuta
(§40): entrena a quien lo lee a ignorarlo, y el día que detecte algo real nadie le hará
caso.

## Grupo 1 — legacy correctamente eliminado, línea base sin actualizar (8 fallos)

`modulos/config_interfaz.py` (pantalla legacy "Apariencia") fue borrado en `6e35244c`.
Seguía figurando en `UI_FILES`, en el snapshot `DOCUMENTED_FINDINGS`, en
`REQUIRED_CANONICAL_FILES` y en `configuracion_scope.json`, de modo que ocho guardrules
exigían la existencia de un archivo cuya eliminación era el objetivo.

Verificado antes de tocar la línea base: existe el reemplazo canónico
(`backend/domain/appearance/` + `frontend/desktop/modules/configuracion/pages/apariencia_page.py`),
el archivo borrado ya estaba roto (referenciaba `theme_service.palettes`/`.densities`
inexistentes) y **ningún módulo productivo lo importa**, así que su borrado no dejó un
import colgando.

Retirarlo de la línea base es ratchetear **hacia abajo**: sus violaciones documentadas
(`currentText: 2`, `except_pass: 1`) llegan a cero por eliminación. Es la dirección
legítima del ratchet, no una tolerancia nueva.

Efecto secundario honesto: hoy **no hay ninguna pantalla de Apariencia** alcanzable desde
el menú legacy. El comentario de `shell_registration.py` que afirmaba que la pantalla
legacy "remains the only thing end users see today" quedó falso y se corrigió.

## Grupo 2 — cola de trabajo desincronizada (1 fallo)

`CONFIGURACION-05-MUTATIONS` se cerró y `work_queue.json` avanzó a
`CONFIGURACION-06-DOMAIN_RULES`, pero el test seguía fijando 05 como lote activo. Se
registra el cierre de 05 y el avance a 06. Esta es exactamente la deriva que el arnés
existe para forzar a documentar.

## Grupo 3 — falsos positivos por coincidencia de texto (3 fallos)

| Guardrail | Marcaba | Por qué era falso |
| --- | --- | --- |
| `test_single_settings_repository_path` | `SettingsRepositoryBase` | `"class SettingsRepository" in src` como subcadena. El legacy real (`repositories/settings_repository.py`) ya no existe; lo marcado es la clase base canónica de Settings |
| `test_no_appcontainer_passed_to_services` | `container: PhysicalContainer` | `container` es también palabra del dominio de Logística: un contenedor físico de envío, no el contenedor DI |
| `test_no_app_container_in_view_or_pages` | el docstring de `supplier_routes.py` | Comparaba texto crudo, así que la frase "never see the connection nor the AppContainer" disparaba el guard que esa misma frase describía |

El tercero merece énfasis: **ese test fallaba por su propia documentación desde antes de
esta remediación**, y su mensaje de error señalaba prosa, no una dependencia.

Cada corrección de precisión lleva **su propia prueba de que el guard sigue detectando lo
real** — `test_dead_settings_repository_pattern_still_catches_the_real_thing`,
`test_domain_container_exemption_does_not_disarm_the_guard` — para que estrechar un patrón
no pueda degenerar en desarmarlo. Los guards de SQL y de colores hexadecimales siguen
leyendo el texto crudo a propósito: lo que buscan sí vive legítimamente dentro de cadenas.

## Grupo 4 — violación real de Service Locator (1 fallo)

`frontend/desktop/modules/finance/suppliers/supplier_routes.py::create_suppliers_view`
resolvía sus dependencias del objeto que recibiera:

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None) or container

Es el Service Locator de frontera que §6 prohíbe, en un archivo cuyo docstring afirmaba lo
contrario. **Tenía cero llamadores**: el consumidor real,
`frontend/desktop/modules/finance/pages/suppliers_page.py`, ya usa
`build_supplier_presenter(connection, session_context)` con ambas dependencias explícitas.

Se elimina en vez de reescribirse (§28/§48: consumidores = 0 → borrar). No se introdujo
ninguna factory nueva para sustituirla porque nada la necesitaba.

## Pruebas y evidencia

Desde `pos_spj_v13.4/` con `QT_QPA_PLATFORM=offscreen`, mismo directorio de trabajo que CI:

```text
python -m pytest tests/architecture -q -p no:cacheprovider --tb=no
```

| Momento | Resultado |
| --- | --- |
| Tras `ecc95744` | 47 failed, 721 passed, 1 skipped |
| Ahora | **34 failed, 736 passed, 1 skipped** |

Diferencia de conjuntos: **13 cerrados, 0 nuevos**.

Comprobaciones dirigidas:

```text
python -m pytest tests/architecture/test_configuracion_guardrails.py \
  tests/architecture/test_configuracion_scope.py \
  tests/architecture/test_configuracion_single_source.py \
  tests/integration/test_configuracion_external_integrations.py -q
```
Resultado: **22 passed** (antes 10 failed / 7 passed).

```text
python -m pytest tests/integration/suppliers/ \
  tests/architecture/test_supplier_ui_guardrails.py -q
```
Resultado: **57 passed** tras eliminar la factory muerta.

## Riesgos residuales

Los 34 fallos abiertos no se han clasificado uno a uno; a la luz de esta fase **no debe
asumirse que todos sean infracciones reales**. Antes de "corregir" código productivo por
cualquiera de ellos hay que leer el assert y confirmar qué marca exactamente. El grupo
`test_refactor_orchestrator.py` (4) es de herramienta de refactor, no de producto.

No hay pantalla de Apariencia alcanzable en el menú legacy; la ruta canónica existe pero
sigue sin cablearse, y ese cutover pertenece a la fase de shell.

## Siguiente fase

Clasificar los 34 restantes separando infracción real de falso positivo antes de tocar
código, empezando por los de identidad (`test_no_int_id_casts`,
`test_no_lastrowid_entity_identity`, `test_uuidv7_cutover_protection`) y esquema
(`test_text_pk_not_null`, `test_no_schema_changes_outside_migrations`), que son los que
sostienen las fases 4 y 7 del plan.
