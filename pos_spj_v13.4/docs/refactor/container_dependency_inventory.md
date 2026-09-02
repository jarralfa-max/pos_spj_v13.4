# SHELL-0 — Inventario de dependencias de `AppContainer`

Metodología: `grep -rE "container\.[a-zA-Z_][a-zA-Z0-9_]*"` sobre todo el
árbol del proyecto (excluyendo `docs/`, `logs/`, `.venv/`, `.git/`), luego
lectura del contexto de cada archivo con ocurrencias significativas para
confirmar que `container` se refiere a `AppContainer` y no a una variable
local homónima (ver §3, falsos positivos).

## 0. Totales

- **142 ocurrencias textuales** de `container.<algo>` en 35 archivos de
  código fuente (excluyendo docs/logs/tests, incluyendo `webapp/` que es JS
  no relacionado a `AppContainer`).
- Descontando `webapp/` (15 ocurrencias, JS de otro contexto, no Python) y
  falsos positivos de variables locales llamadas `container` (ver §3, ~9
  ocurrencias), quedan **~118 consumos reales de `AppContainer`** en
  **~28 archivos Python**.
- **~95 atributos distintos** se cuelgan de `self` dentro de
  `AppContainer.__init__` (repos, servicios, use cases, engines, query
  services) — ver el archivo fuente para el listado línea por línea; no se
  repite aquí completo por volumen, pero cada familia se agrupa en la tabla
  §1.
- `interfaz/main_window.py` es el consumidor más denso con **20 accesos
  reales** (2 de los 22 detectados son falso positivo `logo_container.set*`).
- `modulos/fidelidad_config.py` (17) y `modulos/activos.py` (14) son los
  módulos de negocio que más profundamente perforan el contenedor,
  seguidos de `core/events/wiring.py` (25, pero es infraestructura de
  arranque, no UI — ver nota en §2).

## 1. Familias de atributos colgados de `AppContainer` (por capa)

| Familia | Ejemplos de atributos | Cantidad aprox. | Naturaleza |
|---|---|---|---|
| Conexión / sesión | `db`, `db_path`, `session`, `sucursal_id`, `sucursal_nombre`, `installation_branch_configured` | 7 | Infraestructura + estado de sesión (espejo de `SessionContext`) |
| Repositorios (capa 1) | `config_repo`, `security_repo`, `auth_repo`, `inventory_repository`, `recipe_repo`, `finance_repo`, `sales_repo`, `promo_repo`, `sync_repo`, `cliente_repo`, `producto_repo`, `inventory_write_repository` | 12 | Acceso a datos crudo |
| Servicios fundamentales (capa 2) | `audit_service`, `config_service`, `feature_flag_service`, `security_service`, `auth_service` | 5 | Cross-cutting |
| Servicios de negocio (capa 3) | `inventory_service`/`inventory_application_service`, `finance_service`, `loyalty_service`, `recipe_engine`, `production_engine`, `ticket_template_engine`, `whatsapp_service`, `whatsapp_webhook`, `promotion_engine`, `sync_service`, `customer_credit_service`, `credit_validation_service`, `accounts_receivable_service`, `hardware_service`, `treasury_service`, `asset_service`, `theme_service`, `printer_service`, `qr_parser`, `alert_engine`, `decision_engine`, `actionable_forecast`, `financial_simulator`, `ai_advisor`, `ceo_dashboard`, `franchise_manager`, `expansion_analyzer`, `cotizacion_service`, `app_service` (ERPApplicationService), `comisiones_service`, `anticipo_service`, `event_logger`, `cfdi_service`, `report_engine`, `forecast_engine`, `happy_hour_service`, `analytics_engine`, `bi_dashboard_service`, `bi_settings_service`, `bi_export_service`, `growth_engine`, `discount_guard`, `mercado_pago_service`, `notification_service`, `scheduler_service`, `module_config` | ~44 | El "motor del ERP" — mayoría de la superficie del contenedor |
| Caja canónica (FASE 7.7) | `cash_authorization_policy`, `cash_register_uow_factory`, `cash_*_query_service` (x4), `cash_device_*_uc` (x3), `cash_open_shift_uc`, `cash_suspend_shift_uc`, `cash_resume_shift_uc`, `cash_begin_shift_closing_uc`, `cash_register_movement_uc`, `cash_reverse_movement_uc`, `cash_register_service`, `open_cash_shift_uc`, `register_cash_movement_uc`, `generate_z_cut_uc` | ~20 | Bounded context de caja, ya factorizado con UoW propio |
| Use cases legacy (`uc_*`) | `uc_venta`, `uc_pedido_wa`, `uc_inventario`, `uc_produccion`, `uc_compra`, `uc_cliente`, `uc_finanzas`, `uc_nomina` (siempre `None`, RRHH migrado) | 8 | Capa de orquestación v13.1-13.5, construidos vía `.desde_container(self)` |
| Autorización por sesión viva | `customer_authorization_policy`, `sales_authorization_policy` | 2 | Ya siguen el patrón correcto: reciben `self.session` por referencia viva, no una copia |
| Query services aislados | `inventory_query_service`, `production_query_service` (namespace sintético con `SimpleNamespace`) | 2 | Ya extraídos de UI |

## 2. Consumidores por archivo (file → atributos leídos)

| Consumidor (archivo) | Atributos de `container` leídos | Destino canónico sugerido | Acción |
|---|---|---|---|
| `interfaz/main_window.py` (20 usos reales) | `auth_service`, `set_session_user`, `db` (x7), `session`, `set_sucursal_activa` (x2), `notification_service` (x2), `clear_session` | `ApplicationShellWindow` + `AuthenticationCoordinator` deben recibir estos como colaboradores explícitos inyectados, no vía `self.container.<x>` disperso en 15 métodos distintos | REWRITE — es el consumidor que más se beneficia de un `Protocol`/DTO de sesión explícito (ver hallazgo BLOCKED 3.8 en `application_shell_legacy_inventory.md`) |
| `core/events/wiring.py` (25 usos: `db` x22, `session`, `config_service`, `logistics_application_service`, `logistics_shipment_queries`) | Casi todo `container.db` para construir repos/handlers ad-hoc en tiempo de wiring | Esto es infraestructura de arranque, no UI — `db` aquí es legítimo porque `wiring.py` ES la fábrica de handlers del EventBus | REUSE — mover junto con el contenedor a `infrastructure/messaging/`, sin reescribir la lógica |
| `modulos/fidelidad_config.py` (17 usos, todos `loyalty_service`) | Un solo servicio, repetido 17 veces en vez de guardarse una vez como `self._loyalty = container.loyalty_service` | `LoyaltyService` inyectado directo al constructor del módulo | MOVE — trivial: el módulo ya solo necesita 1 dependencia, no el contenedor completo |
| `modulos/activos.py` (14 usos: `db` x1, `asset_service` x13) | Casi exclusivamente `asset_service` | `AssetService` inyectado directo | MOVE — mismo patrón que fidelidad_config |
| `modulos/ticket_designer.py` (8 usos: `config_service` x6, `db` x1, `ticket_template_engine` x1) | 3 servicios distintos | `ConfigService` + `TicketTemplateEngine` inyectados directo (el `db` suelto debería desaparecer a favor de un repo) | REWRITE — el acceso directo a `db` en un módulo de UI es la violación de regla 13 del skill ("PyQt no debe ejecutar SQL") si se usa para queries; confirmar y extraer si aplica |
| `modulos/delivery.py` (2: `db`, `feature_flag_service`) | 2 servicios | Inyección directa | MOVE |
| `modulos/cotizaciones.py` (3, todos `db`) | Acceso directo a conexión desde UI | `CotizacionRepository`/query service dedicado | REWRITE — mismo riesgo de SQL-en-UI que ticket_designer |
| `modulos/config_modules.py`, `config_hardware.py` (1 c/u, `db`) | Acceso directo a conexión | Repos dedicados | REWRITE |
| `modulos/configuracion.py` (2, `set_sucursal_activa`) | Mutador del contenedor invocado desde UI | Debe pasar por un `BranchConfigurationUseCase` en vez de mutar el contenedor directamente desde una vista | REWRITE |
| `modulos/whatsapp/whatsapp_module.py` (3, `db`) | Acceso directo a conexión | Repo dedicado | REWRITE |
| `modulos/productos_enterprise.py` (2: `session`, `usuario`) | Lee `SessionContext` vía contenedor en vez de recibirlo inyectado | Recibir `SessionContext` directo | MOVE |
| `modulos/planeacion_compras.py` (2: `db`, `forecast_service`) | Mixto | Inyección directa del servicio; retirar `db` suelto | REWRITE |
| `modulos/modulo_growth_engine.py` (4: `db` x1, `loyalty_service` x3) | Mixto | Inyección directa | MOVE |
| `modulos/loyalty_card_designer.py`, `tarjetas.py`, `etiquetas.py`, `config_hardware.py`, `spj_product_search.py` (1 c/u, `db`) | Acceso directo a conexión desde UI | Repos dedicados por módulo | REWRITE |
| `core/use_cases/venta.py` (7: `uc_venta` x2, `sales_service`, `inventory_service`, `finance_service`, `loyalty_service`, `ticket_template_engine`) | Patrón `ProcesarVentaUC.desde_container(self)` — extrae explícitamente cada dependencia nombrada | Ya es el patrón objetivo (factory method que desempaqueta el contenedor UNA vez, en el borde) | **REUSE** — generalizar este patrón a los módulos de arriba en vez de reescribirlo |
| `core/use_cases/{produccion,inventario,cliente}.py` (3 c/u), `core/use_cases/pedido_wa.py` (1) | Mismo patrón `desde_container()` | Igual que arriba | REUSE |
| `core/services/production_application_service.py` (6, `.from_container(self)`) | Mismo patrón factory | Igual que arriba | REUSE |
| `backend/infrastructure/desktop/transfers_factory.py` (4, todos `db`) | Factory dedicada de UI para el bounded context de transferencias — construye repos/UoW a partir de `container.db` únicamente | Ya es exactamente el patrón objetivo (`*_factory.py` que solo toma `db`, no el contenedor completo) | **REUSE** — es el prototipo a copiar para el resto de `modulos/*` (junto con `cash_register_factory.py` y `losses_factory.py`, mencionados en `main_window.py`) |
| `tests/unit/test_remediacion0_raffle_finance_handler.py` (6) | Test unitario que construye un `container` fake/mínimo | N/A (test) | REUSE — fuera de alcance de producción |

## 3. Falsos positivos detectados (variable local llamada `container`, no `AppContainer`)

Confirmados por lectura de contexto — **no** son consumidores del DI
container y deben excluirse de cualquier conteo de refactor:

| Archivo:línea | Qué es realmente |
|---|---|
| `interfaz/main_window.py:312-313` | `logo_container` (un `QFrame` local dentro de `DialogoLogin._configurar_ui`), truncado por el regex a `container.setFixedSize`/`setStyleSheet` |
| `modulos/ui_components.py:497,501,502,711,712` | Parámetro/variable local `container` de tipo `QWidget` en funciones helper de UI genéricas |
| `frontend/desktop/modules/inventory/inventory_view.py:66,67,86` | Variable local `container` (layout wrapper), no `AppContainer` |
| `frontend/desktop/modules/products/products_view.py` (2) | Mismo patrón — confirmar caso a caso antes de tocar |
| `modulos/clientes_crm.py:26` | Comentario que menciona `container.py` como nombre de archivo, no código |

## 4. Patrón ya correcto a generalizar (no reinventar)

Dos patrones **ya existen** en el código y son exactamente el objetivo de
`ModuleRegistry`/view factories de SHELL-6..8:

1. **Factory de UI por bounded context** (`backend/infrastructure/desktop/
   {cash_register_factory,transfers_factory,losses_factory}.py`): reciben
   `container.db` (o un puñado de colaboradores nombrados) y construyen ahí
   mismo repos + UoW + casos de uso + la vista, sin que la vista misma toque
   `container`.
2. **Factory de use case** (`UseCase.desde_container(container)` /
   `.from_container(container)` en `core/use_cases/*.py` y
   `core/services/production_application_service.py`): desempaquetan el
   contenedor una sola vez en un método de clase dedicado, devolviendo un
   objeto ya cableado con dependencias nombradas.

La recomendación para FASE 3/4 no es inventar un mecanismo nuevo — es aplicar
estos dos patrones ya validados (y cubiertos por tests de arquitectura, ver
`tests/architecture/test_sales_pos_ui_does_not_receive_app_container.py`,
`test_customers_crm_ui_does_not_receive_app_container.py`,
`test_no_container_passed_to_services.py` + su
`APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST` en
`tests/architecture/allowlists.py`) al resto de `modulos/*.py` que hoy reciben
`self.container` completo en su constructor (ver lista de 26 módulos
`_conectar()`-eados en `interfaz/main_window.py`, inventariados en
`navigation_route_inventory.md`).

---

*Generado en FASE SHELL-0 (auditoría). No se modificó ningún archivo de aplicación.*
