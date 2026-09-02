# SHELL-0 — Auditoría de arranque (`main.py`, ejecución real)

Traza completa, en orden de ejecución, de lo que hace `main.py` hoy. Basado en
lectura íntegra de `main.py` (279 líneas). Solo lectura — ningún archivo de
aplicación fue modificado.

## 0. Orden de ejecución real (`inicializar_sistema()`)

```
1.  QApplication.setAttribute(AA_ShareOpenGLContexts)     [module-level, antes de import de nada más]
2.  sys.path.insert(0, _BASE_DIR)
3.  setup_logging()                    (fallback: logging.basicConfig + FileHandler)
4.  import version (__version__, __app_name__)
5.  sys.excepthook = _crash_handler    (handler global de excepciones no capturadas)
6.  imports pesados: AppContainer, migrations.engine, MainWindow, bootstrap_database
7.  set_db_path(DB_PATH)               (alinea el pool canónico con la ruta de bootstrap)
--- entra a inicializar_sistema() ---
8.  QApplication(sys.argv) + setApplicationName/Version
9.  load_saved_theme(None)             [try/except]
10. install_dialog_button_normalizer(app) [try/except]
11. _instancia_unica(app)              -> si ya corre, QMessageBox + sys.exit(0)
12. _verificar_bd(DB_PATH)             -> PRAGMA integrity_check; si falla, diálogo
                                          Yes/Ignore/Cancel -> posible _restaurar_backup()
                                          -> si Cancel, sys.exit(1)
13. _bootstrap_db(DB_PATH)             -> ver "Migraciones — ruta A" abajo
14. bootstrap_database(DB_PATH)        -> ver "Migraciones — ruta B" abajo
    [ambas dentro de un mismo try/except; si CUALQUIERA falla -> QMessageBox fatal + sys.exit(1)]
15. bloque de migraciones "oficial"    -> ver "Migraciones — ruta C" abajo
    (migrator.up + migrate_db + verificar_tablas + assert_uuid_identity)
    - IntegerIdentityError -> QMessageBox fatal + sys.exit(1)   (REGLA CERO gate)
    - RuntimeError         -> QMessageBox fatal + sys.exit(1)   (BD incompleta)
    - Exception genérica   -> logger.error(...) y CONTINÚA (no sale del proceso)
16. AppContainer(db_path=DB_PATH)      -> si falla, QMessageBox fatal + sys.exit(1)
17. launch_microservice_async(app_root) [try/except, no fatal]
18. container.whatsapp_webhook.start() [try/except, no fatal, gateado por hasattr]
19. MainWindow(container) + .show()    -> si falla, QMessageBox fatal + sys.exit(1)
20. VersionChecker(...).check_async(...) [try/except, no fatal]
21. app.exec_()                        (Qt event loop — el proceso vive aquí)
--- al salir del event loop ---
22. cleanup loop: whatsapp_webhook.stop() -> container.close() -> _LOCAL_SERVER.close()
    (cada uno en su propio try/except: pass — sin logging de fallo de cleanup)
23. logger.info("Sistema cerrado...") + sys.exit(exit_code)
```

## 1. Migraciones: TRES rutas ejecutadas en el mismo arranque

Este es el hallazgo más importante de la auditoría de bootstrap.

**Ruta A — `_bootstrap_db(DB_PATH)` (paso 13, definida en `main.py` líneas 53-74):**
```python
try:
    from scripts.bootstrap_db import bootstrap_database
    bootstrap_database(db_path)
    return
except Exception as e:
    logger.warning("bootstrap_db externo no disponible (%s). Usando fallback interno.", e)

# Fallback interno si el import/llamada de arriba falló:
conn = sqlite3.connect(db_path)              # <-- conexión CRUDA, sin WAL/busy_timeout/FK
migrator.up(conn)
migrate_db(conn)
verificar_tablas(conn)
conn.close()
```
Nótese que esta función **ya llama a `bootstrap_database()` internamente** en su
camino feliz.

**Ruta B — `bootstrap_database(DB_PATH)` (paso 14, llamada de nuevo, directa):**
Inmediatamente después de `_bootstrap_db()`, `main.py` llama otra vez a
`bootstrap_database(DB_PATH)` de forma independiente — es decir, en el camino
feliz, `scripts.bootstrap_db.bootstrap_database()` se invoca **dos veces
consecutivas** en la misma ejecución (una dentro de `_bootstrap_db`, otra
explícita).

**Ruta C — bloque "oficial" de migraciones (paso 15, líneas 182-217):**
```python
conn = sqlite3.connect(DB_PATH)              # <-- otra conexión CRUDA más
migrator.up(conn)
migrate_db(conn)
verificar_tablas(conn)
assert_uuid_identity(conn)                   # gate REGLA CERO
conn.close()
```
Esto vuelve a llamar `migrator.up()` + `migrate_db()` + `verificar_tablas()` —
las mismas tres llamadas que ya hizo el fallback de la Ruta A (si tomó ese
camino) — y agrega el gate `assert_uuid_identity`.

**Por qué no corrompe datos (mitigante):** `migrations/engine.py` está
diseñado para ser idempotente — usa una tabla `schema_migrations` con
`INSERT OR IGNORE` y cada migración individual usa `CREATE TABLE IF NOT
EXISTS` / `ALTER TABLE` seguro (confirmado leyendo el encabezado de
`engine.py`: *"Idempotente: usa CREATE TABLE IF NOT EXISTS y ALTER TABLE
seguro. Registra cada migración ejecutada en la tabla schema_migrations."*).
Por eso ejecutar `migrator.up()` 1-2 veces por arranque no debería re-aplicar
una migración ya registrada.

**Por qué sigue siendo un riesgo real:**
- Cada ruta abre su **propia conexión `sqlite3.connect()` cruda**, sin pasar
  por `core.db.connection.get_connection()` (que configura WAL, `busy_timeout`,
  `PRAGMA foreign_keys=ON`). Tres `sqlite3.connect()` independientes contra el
  mismo archivo, cada una con su propio `.close()`, en la ventana de arranque
  más sensible del proceso (antes de que exista ningún lock coordinador más
  allá de SQLite mismo).
- El único punto que efectivamente **bloquea el arranque** por identidad
  UUIDv7 (`assert_uuid_identity`) vive solo en la Ruta C. Si la Ruta A o B
  fallaran de forma que dejaran la BD en un estado intermedio pero sin lanzar
  excepción, el gate de la Ruta C podría no alcanzar a ejecutarse de la forma
  esperada según cuál excepción se dispare antes.
- Tiempo de arranque: en el peor caso (fallback de Ruta A activado),
  `migrator.up()` se ejecuta hasta 2 veces completas antes de que la app
  muestre la ventana de login — overhead innecesario en cada arranque, no solo
  en el primero.
- Es una violación directa de la regla de skill *"11. Solo `migrations/` puede
  modificar schema"* combinada con *"Toda dependencia debe inyectarse
  explícitamente"*: aquí hay 3 puntos de entrada al motor de migraciones
  coexistiendo por acumulación histórica, no por diseño.

**Recomendación para SHELL-2 (bootstrapper):** colapsar las 3 rutas en una
sola llamada `CompositionRoot.bootstrap_database()` que:
1. Abra una única conexión vía `core.db.connection.get_connection()`.
2. Ejecute `migrator.up()` → `migrate_db()` → `verificar_tablas()` →
   `assert_uuid_identity()` en ese orden, una sola vez.
3. Elimine `scripts/bootstrap_db.bootstrap_database()` como ruta paralela o
   lo convierta en la única implementación que las otras dos invocan (no al
   revés).

## 2. Excepciones tragadas silenciosamente ("silent startup failure")

Inventario de cada `except` en el camino de arranque y su efecto real:

| Ubicación | Qué atrapa | Efecto si ocurre | ¿Bloquea el arranque? |
|---|---|---|---|
| `setup_logging()` import | Cualquier excepción | Cae a `logging.basicConfig` mínimo | No — degradación aceptable |
| `load_saved_theme(None)` | Cualquier excepción | Tema no aplicado, solo `logger.warning` | No |
| `install_dialog_button_normalizer(app)` | Cualquier excepción | Normalizador de botones no activo | No |
| Migraciones — bloque paso 15, rama `except Exception as e` (no `IntegerIdentityError`/`RuntimeError`) | Cualquier otra excepción de `migrator.up`/`migrate_db`/`verificar_tablas` | **`logger.error(...)` y el proceso CONTINÚA** hacia `AppContainer(...)` | **No — y debería.** Este es el hallazgo de mayor riesgo de todo el bootstrap: cualquier fallo de migración que no sea exactamente `IntegerIdentityError` o `RuntimeError` dinamita el gate de integridad y dej a la app arrancar sobre un esquema potencialmente incompleto, confiando en que "los repositorios harán fallback". |
| `launch_microservice_async(...)` | Cualquier excepción | Microservicio WhatsApp no arranca, solo `logger.debug` | No |
| `container.whatsapp_webhook.start()` | Cualquier excepción | Webhook no arranca, solo `logger.warning` | No |
| `VersionChecker(...)` | Cualquier excepción | `except Exception: pass` — **ni siquiera loguea** | No |
| Cleanup final (3 lambdas) | Cualquier excepción por lambda | `except Exception: pass` — sin logging | N/A (shutdown) |

**Conclusión:** de todos los `except` del arranque, exactamente **uno** es
genuinamente peligroso: el `except Exception` genérico del bloque de
migraciones (paso 15) que permite continuar. Todos los demás son
degradaciones aceptables de funcionalidad no crítica (tema, microservicio,
notificador de versión) correctamente aisladas con `try/except` + logging.

## 3. Puntos de salida forzada (`sys.exit`)

| Código | Condición | Mensaje al usuario |
|---|---|---|
| `sys.exit(0)` | Ya hay una instancia corriendo (`_instancia_unica`) | "Ya está ejecutándose" |
| `sys.exit(1)` | `_verificar_bd` devuelve False (usuario canceló restauración de BD dañada) | (diálogo previo de `_verificar_bd`) |
| `sys.exit(1)` | `_bootstrap_db` + `bootstrap_database` lanzan excepción | "Error Fatal — Bootstrap DB" |
| `sys.exit(1)` | `IntegerIdentityError` (REGLA CERO: BD sin cortar a UUIDv7) | "Error Fatal — Identidad UUIDv7 requerida" |
| `sys.exit(1)` | `RuntimeError` (BD incompleta post-migraciones) | "Error Fatal — DB incompleta" |
| `sys.exit(1)` | `AppContainer(...)` lanza excepción | "Error Fatal" genérico |
| `sys.exit(1)` | `MainWindow(container)` lanza excepción | "Error Fatal" genérico |
| `sys.exit(exit_code)` | Fin normal del event loop (`app.exec_()`) | — |

Los gates de `sys.exit(1)` están correctamente ubicados para los casos que sí
cubren (BD dañada, identidad UUIDv7 no cortada, `AppContainer`/`MainWindow`
rotos). El hueco es únicamente el `except Exception` descrito en §2.

## 4. Orden de dependencias observado (para el futuro `CompositionRoot`)

```
logging → version → excepthook → AppContainer/migrations/MainWindow/bootstrap_db (imports)
   → set_db_path
   → QApplication
   → tema + normalizador de diálogos (UI-level, no bloqueante)
   → single-instance lock
   → integridad de BD (PRAGMA integrity_check)
   → bootstrap de esquema (triplicado, ver §1)
   → AppContainer (que a su vez construye ~35 repos + ~60 servicios + scheduler + event bus wiring)
   → microservicio WhatsApp (async, no bloqueante)
   → webhook WhatsApp (síncrono pero best-effort)
   → MainWindow (que dispara mostrar_login() en su primer showEvent)
   → VersionChecker (async, no bloqueante)
   → event loop
```

`AppContainer` es, en la práctica, un segundo bootstrapper completo anidado
dentro del primero — construye scheduler, wiring de EventBus y ~95
dependencias en su `__init__`. Ver `container_dependency_inventory.md` para el
detalle.

## 5. Duplicación de secuencias de bootstrap — resumen

1. `bootstrap_database(DB_PATH)` se invoca 2 veces en el camino feliz (dentro
   de `_bootstrap_db` y explícitamente después).
2. `migrator.up()` + `migrate_db()` + `verificar_tablas()` se invocan hasta 2
   veces completas (fallback interno de `_bootstrap_db` + bloque "oficial").
3. Tres conexiones `sqlite3.connect()` crudas distintas se abren y cierran
   durante el arranque, además de la conexión canónica pooled que usa
   `AppContainer`.

Ninguna de las tres rutas está protegida por un lock explícito entre sí más
allá de que SQLite serializa escrituras — el único lock de proceso real es
`_instancia_unica()` (QLocalServer), que sí es correcto y previene dos
*procesos* concurrentes, pero no previene la redundancia *dentro* de un mismo
proceso.

---

*Generado en FASE SHELL-0 (auditoría). No se modificó ningún archivo de aplicación.*
