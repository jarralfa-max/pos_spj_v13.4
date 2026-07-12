# SPJ UI/UX + Architecture Refactor Skill

> Skill operativo para refactorizar SPJ POS v13.4 con enfoque exclusivo en UI/UX profesional, arquitectura limpia, reubicación obligatoria de módulos a la estructura objetivo de `SPJ_REFACTOR_SKILL.md`, compatibilidad tema claro/oscuro, componentes visuales estándar y gráficas generadas con HTML + JavaScript.

---

## 0. Contexto obligatorio

La aplicación SPJ POS v13.4 está en **desarrollo activo**.

Por lo tanto:

* No se requieren migraciones de rescate.
* No se deben conservar datos legacy.
* No se deben crear capas de compatibilidad temporal.
* No se debe invertir esfuerzo en salvar bases locales contaminadas.
* La base de desarrollo puede y debe resetearse cuando sea necesario.
* El éxito del refactor es que el código actual cree una aplicación limpia, profesional, coherente y born-clean desde cero.

Este skill complementa y debe respetar siempre:

```text
pos_spj_v13.4/docs/skills/SPJ_REFACTOR_SKILL.md
```

Si existe conflicto entre este skill y `SPJ_REFACTOR_SKILL.md`, gana `SPJ_REFACTOR_SKILL.md`.

---

## 1. Objetivo

Transformar la interfaz y la arquitectura visual del sistema para que SPJ POS parezca una aplicación empresarial desarrollada por un equipo experto.

La UI debe ser:

* Profesional.
* Moderna.
* Consistente.
* Compatible con tema claro y oscuro.
* Sin estilos hardcodeados por pantalla.
* Sin layouts sobrepuestos.
* Sin textos cortados.
* Sin apariencia de aplicación escolar.
* Sin lógica de negocio en widgets PyQt.
* Sin SQL en UI.
* Con gráficas renderizadas mediante HTML + JavaScript.
* Con módulos reubicados progresivamente en la estructura objetivo del refactor.

Este skill no solo mejora cómo se ve la app. También obliga a mover cada módulo intervenido a la arquitectura correcta.

---

## 2. Reglas no negociables

### 2.1 Arquitectura

Está prohibido:

```text
- Ejecutar SQL desde PyQt.
- Hacer commit() o rollback() desde UI.
- Crear o alterar tablas desde UI.
- Calcular lógica de negocio dentro de widgets.
- Calcular KPIs dentro de pantallas PyQt.
- Pasar AppContainer completo a servicios nuevos.
- Usar defaults arbitrarios en campos visibles.
- Crear migraciones de rescate durante desarrollo.
- Mantener compatibilidad legacy innecesaria.
- Agregar lógica nueva a carpetas legacy.
```

Toda lectura para UI debe pasar por:

```text
QueryService
```

Toda mutación funcional debe pasar por:

```text
UseCase / ApplicationService
```

Toda persistencia debe pasar por:

```text
Repository
```

La UI solo debe:

```text
- Presentar datos.
- Capturar entradas.
- Emitir acciones.
- Mostrar resultados.
- Renderizar componentes visuales.
```

---

### 2.2 UI/UX

Está prohibido:

```text
- Colores hexadecimales hardcodeados en pantallas.
- setStyleSheet() con colores dentro de módulos.
- Botones creados directo sin factory o variante estándar.
- KPIs creados con implementaciones distintas.
- Tablas sin política visual común.
- Diálogos con botones full-width no intencionales.
- Layouts con widgets sobrepuestos.
- Textos cortados en tablas, cards, labels o botones.
- Gráficas nativas de PyQt.
- Pantallas nuevas en carpetas legacy.
```

Todo color, tamaño, borde, spacing, tipografía y estado visual debe venir de:

```text
design_tokens.py
qss_builder.py
theme_manager.py
```

---

### 2.3 Gráficas

Todas las gráficas deben generarse con:

```text
HTML + JavaScript
```

Está prohibido:

```text
- Dibujar gráficas con PyQt nativo.
- Calcular datos de gráfica dentro del widget.
- Hardcodear colores de gráfica en la pantalla.
- Repetir templates HTML por módulo.
- Crear gráficas con lógica visual dispersa.
```

Arquitectura obligatoria:

```text
QueryService
  ↓
ChartData DTO
  ↓
HtmlChartView
  ↓
HTML template
  ↓
JavaScript renderer
```

Librería recomendada:

```text
Apache ECharts
```

También se permite `Chart.js` o `ApexCharts` si existe justificación, pero debe mantenerse una sola estrategia canónica para el sistema.

---

## 3. Regla obligatoria de reubicación estructural

Este refactor **no solo estandariza UI/UX**. También debe mover progresivamente los módulos existentes a la arquitectura objetivo definida por `SPJ_REFACTOR_SKILL.md`.

La estructura legacy actual:

```text
modulos/
interfaz/
ui/
services/
repositories/
core/
```

no debe seguir creciendo como destino principal.

A partir de este skill, todo código nuevo o refactorizado debe moverse a:

```text
frontend/
  desktop/
    modules/
    components/
    themes/
    charts/
    i18n/

backend/
  domain/
  application/
    use_cases/
    commands/
    dto/
    queries/
    event_handlers/
  infrastructure/
    db/
    hardware/
    maps/
    printers/
    whatsapp/
    updater/
  api/
  shared/
    events/
    errors/
    result.py
    app_paths.py
    ids.py
```

---

### 3.1 Regla no negociable

Cuando se toque un módulo por UI/UX o arquitectura, **queda prohibido dejarlo únicamente en su ubicación legacy**.

Cada módulo intervenido debe terminar con su estructura nueva creada dentro de:

```text
frontend/desktop/modules/<module_name>/
backend/application/
backend/domain/
backend/infrastructure/
```

según corresponda.

Ejemplo:

```text
ANTES:
modulos/productos.py

DESPUÉS:
frontend/desktop/modules/products/products_view.py
frontend/desktop/modules/products/products_presenter.py
backend/application/queries/product_query_service.py
backend/application/use_cases/create_product_use_case.py
backend/application/use_cases/update_product_use_case.py
backend/application/dto/product_dto.py
backend/domain/products/
backend/infrastructure/db/repositories/product_repository.py
```

El archivo legacy puede quedar temporalmente solo como wrapper de compatibilidad, pero no debe contener lógica nueva.

---

### 3.2 Prohibido seguir agregando lógica a carpetas legacy

Está prohibido agregar nueva lógica funcional, visual o arquitectónica en:

```text
modulos/
interfaz/
ui/
services/
repositories/
core/
```

salvo que sea:

```text
- wrapper temporal de compatibilidad;
- import bridge hacia la nueva estructura;
- eliminación de código muerto;
- parche mínimo para no romper arranque durante la transición.
```

Toda lógica nueva debe nacer en la estructura objetivo.

---

### 3.3 Wrappers legacy permitidos solo temporalmente

Se permite mantener wrappers como:

```python
# modulos/productos.py
from frontend.desktop.modules.products.products_view import ProductsView
```

Pero el wrapper:

```text
[ ] No debe contener SQL.
[ ] No debe contener lógica de negocio.
[ ] No debe contener estilos.
[ ] No debe contener layouts complejos.
[ ] No debe calcular KPIs.
[ ] No debe renderizar gráficas.
[ ] No debe crear tablas.
[ ] No debe persistir datos.
```

Su único propósito es evitar romper imports existentes mientras se actualiza navegación.

---

### 3.4 Cada módulo debe dividirse en capas

Cada módulo migrado debe separar responsabilidades así:

```text
frontend/desktop/modules/<module>/
  <module>_view.py          # Solo UI PyQt
  <module>_presenter.py     # Orquestación ligera de UI
  <module>_models.py        # Modelos de vista, no entidades de dominio
  <module>_routes.py        # Registro/navegación si aplica

backend/application/queries/
  <module>_query_service.py # Lecturas para UI

backend/application/use_cases/
  <action>_<module>_use_case.py # Mutaciones

backend/application/dto/
  <module>_dto.py           # Datos limpios para UI/API

backend/domain/<module>/
  entities.py
  policies.py
  services.py

backend/infrastructure/db/repositories/
  <module>_repository.py
```

La UI no debe importar directamente repositorios ni conexión de base de datos.

---

### 3.5 Regla de imports

Permitido en UI:

```python
from frontend.desktop.components import ...
from frontend.desktop.themes.theme_manager import ThemeManager
from backend.application.queries.product_query_service import ProductQueryService
from backend.application.use_cases.create_product_use_case import CreateProductUseCase
from backend.application.dto.product_dto import ProductDTO
```

Prohibido en UI:

```python
import sqlite3
from core.db.connection import get_connection
from repositories.product_repository import ProductRepository
from services.product_service import ProductService

conn.execute(...)
cursor.execute(...)
commit()
rollback()
```

---

### 3.6 Mapa obligatorio de migración por módulo

Crear y mantener:

```text
docs/refactor/module_relocation_map.md
```

Con esta tabla:

```text
| Módulo | Legacy actual | Frontend nuevo | Backend nuevo | Estado | Wrapper legacy | Pendiente |
| ------ | ------------- | -------------- | ------------- | ------ | -------------- | --------- |
| productos | modulos/productos.py | frontend/desktop/modules/products/ | backend/application/... | IN_PROGRESS | Sí | mover tablas |
```

Estados permitidos:

```text
NOT_STARTED
IN_PROGRESS
WRAPPED
MIGRATED
LEGACY_REMOVED
BLOCKED
```

Un módulo no puede marcarse como `MIGRATED` mientras siga teniendo lógica funcional en `modulos/`, `interfaz/` o `ui/`.

---

### 3.7 Orden obligatorio de reubicación

Migrar en este orden:

```text
1. Configuración / tema
2. Componentes compartidos UI
3. Dashboard / BI
4. Productos
5. Inventario
6. Compras
7. Transferencias
8. Caja
9. Ventas
10. Clientes
11. Delivery
12. WhatsApp
13. Fidelidad / tarjetas
14. Finanzas
15. RRHH
16. Activos
17. Tickets / etiquetas
18. Hardware
```

La razón es que configuración, tema y componentes compartidos deben quedar primero, porque las demás pantallas dependerán de ellos.

---

### 3.8 Criterio de aceptación por módulo reubicado

Un módulo se considera correctamente reubicado solo si cumple:

```text
[ ] Tiene carpeta en frontend/desktop/modules/<module>/.
[ ] Su UI vive en <module>_view.py.
[ ] Su lógica de presentación vive en <module>_presenter.py o equivalente.
[ ] Sus lecturas vienen de backend/application/queries/.
[ ] Sus mutaciones vienen de backend/application/use_cases/.
[ ] Sus DTOs viven en backend/application/dto/.
[ ] Sus reglas de negocio viven en backend/domain/<module>/.
[ ] Su persistencia vive en backend/infrastructure/db/repositories/.
[ ] El archivo legacy solo reexporta o delega.
[ ] No hay SQL en UI.
[ ] No hay estilos hardcodeados en UI.
[ ] No hay gráficos PyQt nativos.
[ ] Las gráficas usan HTML + JavaScript.
[ ] Usa componentes estándar desde frontend/desktop/components/.
[ ] Está registrado en docs/refactor/module_relocation_map.md.
[ ] Tiene tests de arquitectura actualizados.
```

---

### 3.9 Tests obligatorios de reubicación

Crear o actualizar:

```text
tests/architecture/test_modules_are_in_target_structure.py
tests/architecture/test_no_new_logic_in_legacy_modules.py
tests/architecture/test_frontend_does_not_import_repositories.py
tests/architecture/test_frontend_does_not_import_db_connection.py
tests/architecture/test_legacy_wrappers_are_thin.py
```

Estos tests deben validar:

```text
[ ] Ningún módulo nuevo nace en modulos/.
[ ] Ninguna pantalla nueva nace en interfaz/.
[ ] Ningún componente nuevo nace en ui/.
[ ] frontend/desktop/modules no importa sqlite3.
[ ] frontend/desktop/modules no importa repositories directamente.
[ ] frontend/desktop/modules no importa core.db.connection.
[ ] Los wrappers legacy tienen tamaño mínimo y solo delegan.
[ ] El mapa de reubicación está actualizado.
```

---

### 3.10 Política de eliminación legacy

Después de migrar cada módulo:

```text
1. Confirmar que la navegación usa la nueva vista.
2. Confirmar que los imports legacy ya no son necesarios.
3. Confirmar que los tests pasan.
4. Eliminar archivo legacy si ya no se usa.
5. Actualizar module_relocation_map.md.
6. Marcar estado como LEGACY_REMOVED.
```

No se debe conservar código legacy “por si acaso”.

---

### 3.11 Definición estructural de terminado

El refactor UI/UX + arquitectura no se considera terminado hasta que:

```text
[ ] Los módulos principales viven en frontend/desktop/modules/.
[ ] Los componentes compartidos viven en frontend/desktop/components/.
[ ] Los temas viven en frontend/desktop/themes/.
[ ] Las gráficas viven en frontend/desktop/charts/.
[ ] Las lecturas viven en backend/application/queries/.
[ ] Las mutaciones viven en backend/application/use_cases/.
[ ] Los DTOs viven en backend/application/dto/.
[ ] Las reglas de negocio viven en backend/domain/.
[ ] La persistencia vive en backend/infrastructure/db/repositories/.
[ ] modulos/ ya no contiene lógica funcional principal.
[ ] interfaz/ ya no contiene pantallas principales.
[ ] ui/ ya no contiene componentes nuevos.
[ ] services/ y repositories/ legacy ya no reciben lógica nueva.
[ ] La app arranca desde la nueva estructura.
[ ] Los wrappers legacy fueron eliminados o quedan justificados temporalmente.
```

Principio obligatorio:

```text
No basta con mejorar cómo se ve.
Debe quedar ubicado donde arquitectónicamente pertenece.
```

---

## 4. Estructura objetivo mínima para este refactor

Crear o consolidar la siguiente estructura dentro de:

```text
pos_spj_v13.4/pos_spj_v13.4/
```

Estructura requerida:

```text
frontend/
  desktop/
    modules/
      dashboard/
      products/
      inventory/
      purchases/
      transfers/
      cash/
      sales/
      customers/
      settings/
      delivery/
      whatsapp/
      loyalty/
      finance/
      hr/
      assets/
      tickets/
      hardware/

    components/
      buttons.py
      inputs.py
      tables.py
      kpi_card.py
      kpi_bar.py
      page_header.py
      cards.py
      dialogs.py
      empty_state.py
      chart_view.py

    themes/
      tokens.py
      qss_builder.py
      theme_manager.py

    charts/
      templates/
        chart_base.html
      renderers/
        echarts_renderer.js
      chart_bridge.py

    i18n/
      es_mx.py

backend/
  application/
    dto/
      chart_data.py
    queries/
      settings_query_service.py
      business_intelligence_query_service.py
    use_cases/
      update_user_theme_use_case.py

  domain/

  infrastructure/
    db/
      repositories/

tests/
  architecture/
    test_no_sql_in_frontend.py
    test_no_commit_rollback_in_frontend.py
    test_no_hardcoded_ui_colors.py
    test_ui_uses_standard_components.py
    test_charts_are_html_js.py
    test_modules_are_in_target_structure.py
    test_no_new_logic_in_legacy_modules.py
```

Si ya existen componentes equivalentes en `modulos/`, no romperlos de golpe. Crear wrappers temporales y migrar pantalla por pantalla.

---

## 5. Fase 0 — Rama de trabajo y guardrails

Crear rama dedicada:

```bash
git checkout main
git pull
git checkout -b refactor/ui-ux-architecture-clean
```

Objetivo:

```text
Bloquear nuevas infracciones antes de tocar pantallas.
```

Tareas:

```text
1. Crear tests de arquitectura para impedir SQL en frontend.
2. Crear tests para impedir commit/rollback en UI.
3. Crear tests para detectar colores hardcodeados fuera de tokens/QSS.
4. Crear tests para validar uso de componentes estándar.
5. Crear tests para validar que gráficas usan HTML + JavaScript.
6. Crear tests para obligar reubicación de módulos a la estructura objetivo.
7. Crear allowlist temporal solo para deuda existente.
8. Documentar la deuda, pero impedir que aumente.
```

Criterio de salida:

```text
[ ] Los tests actuales pasan.
[ ] Los nuevos tests pasan con allowlist inicial.
[ ] Toda nueva infracción queda bloqueada.
[ ] La deuda está registrada y clasificada.
[ ] Existe module_relocation_map.md.
```

---

## 6. Fase 1 — Sistema visual único

Archivos base a consolidar o mover:

```text
modulos/design_tokens.py
modulos/qss_builder.py
ui/themes/theme_engine.py
modulos/ui_components.py
modulos/kpi_card.py
```

Destino final:

```text
frontend/desktop/themes/tokens.py
frontend/desktop/themes/qss_builder.py
frontend/desktop/themes/theme_manager.py
frontend/desktop/components/
```

Tareas:

```text
1. Consolidar tokens de color, tipografía, spacing, bordes y sombras.
2. Separar tokens de tema claro y oscuro.
3. Definir tokens específicos para:
   - botones
   - inputs
   - tablas
   - KPI cards
   - cards
   - diálogos
   - charts
   - sidebar
4. Eliminar colores hardcodeados en widgets.
5. Mover colores inline al QSS global.
6. Usar objectName y property("variant") para estilos.
7. Mantener sidebar oscuro solo como excepción documentada de producto.
8. Dejar wrappers legacy en modulos/ solo si son necesarios temporalmente.
```

Criterio de salida:

```text
[ ] frontend/desktop/themes/tokens.py es la fuente de verdad visual.
[ ] frontend/desktop/themes/qss_builder.py genera tema claro y oscuro.
[ ] frontend/desktop/themes/theme_manager.py solo aplica tema.
[ ] No hay estilos visuales duplicados entre módulos.
[ ] modulos/design_tokens.py y modulos/qss_builder.py solo delegan o quedan eliminados.
```

---

## 7. Fase 2 — Componentes UI canónicos

Crear componentes oficiales:

```text
frontend/desktop/components/buttons.py
frontend/desktop/components/inputs.py
frontend/desktop/components/tables.py
frontend/desktop/components/kpi_card.py
frontend/desktop/components/kpi_bar.py
frontend/desktop/components/page_header.py
frontend/desktop/components/cards.py
frontend/desktop/components/dialogs.py
frontend/desktop/components/empty_state.py
frontend/desktop/components/chart_view.py
```

---

### 7.1 Botones

Variantes obligatorias:

```text
primary
secondary
success
warning
danger
outline
ghost
table_action
icon
```

Tamaños estándar:

```text
Button.SM = 28 px
Button.MD = 32 px
Button.LG = 36 px
TableActionButton = 24–26 px
IconButton = 32 o 36 px
DialogButton = 32 px
```

Reglas:

```text
[ ] Ningún botón nuevo se crea directo con QPushButton sin factory.
[ ] Ningún botón define color inline.
[ ] Ningún botón se expande a todo el ancho salvo que el layout lo requiera explícitamente.
[ ] Todos los diálogos usan botones estándar.
```

---

### 7.2 KPI cards y KPI bar

Debe existir una sola implementación canónica:

```text
frontend/desktop/components/kpi_card.py
frontend/desktop/components/kpi_bar.py
```

Reglas:

```text
[ ] Altura KPI estándar: 96–112 px.
[ ] Icono KPI estándar: 36 px.
[ ] Valor KPI con tipografía uniforme.
[ ] Título KPI uppercase o semántica uniforme.
[ ] Barra de acento controlada por variant.
[ ] Compatible claro/oscuro.
[ ] Sin estilos inline de color.
```

Eliminar o convertir en wrappers:

```text
modulos/kpi_card.py
create_stat_card()
create_kpi_card()
create_kpi_bar()
```

---

### 7.3 Tablas

Crear `StandardTable`.

Política obligatoria:

```text
rowHeight mínimo: 32 px
headerHeight mínimo: 32 px
wordWrap en columnas descriptivas
tooltip automático con texto completo
IDs internos ocultos
columnas descriptivas con Stretch
columnas numéricas con ResizeToContents
columnas de fecha/estado con ResizeToContents
columna acciones con ancho fijo
scroll horizontal cuando sea necesario
```

Reglas:

```text
[ ] Ningún texto importante debe cortarse.
[ ] Todas las tablas deben verse iguales.
[ ] Las acciones por fila no deben romper altura.
[ ] Los headers deben ser legibles.
[ ] El contraste debe funcionar en claro y oscuro.
```

---

### 7.4 PageHeader

Toda pantalla debe iniciar con:

```text
PageHeader
```

Debe soportar:

```text
- título
- subtítulo
- acciones a la derecha
- modo compacto
- separador opcional
```

Reglas:

```text
[ ] Ninguna pantalla debe construir headers manuales repetidos.
[ ] Los botones del header usan factories.
[ ] El header no debe sobreponerse a contenido.
```

---

### 7.5 Dialogs

Crear `StandardDialog`.

Reglas:

```text
[ ] Botones estándar.
[ ] Márgenes uniformes.
[ ] Títulos consistentes.
[ ] Soporte claro/oscuro.
[ ] Sin estilos inline.
[ ] Sin botones full-width accidentales.
[ ] Sin inputs comprimidos.
```

---

## 8. Fase 3 — Gráficas HTML + JavaScript

Crear:

```text
frontend/desktop/components/chart_view.py
frontend/desktop/charts/templates/chart_base.html
frontend/desktop/charts/renderers/echarts_renderer.js
frontend/desktop/charts/chart_bridge.py
backend/application/dto/chart_data.py
```

---

### 8.1 ChartData DTO

Contrato sugerido:

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ChartData:
    chart_id: str
    chart_type: str
    title: str
    subtitle: str | None
    labels: list[str]
    series: list[dict[str, Any]]
    options: dict[str, Any]
    theme: str
```

---

### 8.2 HtmlChartView

Responsabilidades:

```text
- Cargar template HTML.
- Inyectar JSON seguro.
- Aplicar tema actual.
- Renderizar con JavaScript.
- No calcular métricas.
- No ejecutar SQL.
- No definir colores inline.
```

---

### 8.3 JavaScript renderer

Debe manejar:

```text
- line
- bar
- pie
- doughnut
- area
- stacked_bar
- heatmap
- gauge
```

Criterio de salida:

```text
[ ] Toda gráfica usa HTML + JavaScript.
[ ] No existen gráficas PyQt nativas.
[ ] Los datos vienen desde QueryService.
[ ] Los colores salen de tokens/tema.
[ ] Ejes, tooltips y leyendas son legibles en claro/oscuro.
```

---

## 9. Fase 4 — Sacar SQL de UI

Orden recomendado:

```text
1. Configuración / tema
2. Dashboard / BI
3. Inventario
4. Productos
5. Compras
6. Transferencias
7. Caja
8. Ventas
9. Clientes
10. Finanzas / RRHH / Activos
```

Patrón obligatorio:

```text
ANTES:
Pantalla PyQt → SQL directo / cálculo / commit

DESPUÉS:
Pantalla PyQt → QueryService / UseCase → Repository
```

Ejemplo para tema:

```text
ANTES:
theme_engine.py lee/escribe configuraciones con SQL directo.

DESPUÉS:
ThemeManager solo aplica QSS.
SettingsQueryService lee configuración.
UpdateUserThemeUseCase guarda preferencia.
SettingsRepository persiste.
```

Criterio de salida:

```text
[ ] PyQt no contiene SELECT.
[ ] PyQt no contiene INSERT.
[ ] PyQt no contiene UPDATE.
[ ] PyQt no contiene DELETE.
[ ] PyQt no contiene CREATE TABLE.
[ ] PyQt no contiene ALTER TABLE.
[ ] PyQt no contiene commit().
[ ] PyQt no contiene rollback().
```

---

## 10. Fase 5 — Base limpia de desarrollo

Como la app está en desarrollo, no crear migraciones de rescate.

Cuando una base local esté contaminada, resetear:

```powershell
cd "C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\pos_spj_v13.4"
Copy-Item ".\data\spj_pos_database.db" ".\data\spj_pos_database_backup_dev_reset.db" -ErrorAction SilentlyContinue
Remove-Item ".\data\spj_pos_database.db" -ErrorAction SilentlyContinue
python main.py
```

Reglas:

```text
[ ] No crear migraciones para salvar datos locales.
[ ] No crear lectura dual.
[ ] No crear escritura dual.
[ ] No crear fallback legacy.
[ ] No usar sucursal default 1.
[ ] No usar IDs enteros funcionales.
[ ] Corregir el schema fuente para que nazca limpio.
```

---

## 11. Fase 6 — Migración visual y estructural por pantalla

Orden recomendado por impacto:

```text
1. MainWindow + MenuLateral
2. Dashboard / BI
3. Ventas
4. Productos
5. Inventario
6. Compras
7. Transferencias
8. Caja
9. Clientes
10. Configuración
11. RRHH
12. Finanzas
13. Activos
14. WhatsApp
15. Delivery
16. Tickets / etiquetas
17. Hardware
```

Checklist por pantalla:

```text
[ ] Vive en frontend/desktop/modules/<module>/.
[ ] Usa PageHeader.
[ ] Usa KPIBar oficial.
[ ] Usa StandardTable.
[ ] Usa botones factory.
[ ] Usa cards estándar.
[ ] Usa StandardDialog donde aplique.
[ ] Usa scroll cuando el contenido pueda crecer.
[ ] No hay widgets sobrepuestos.
[ ] No hay textos cortados.
[ ] No hay colores inline.
[ ] No hay SQL.
[ ] No hay commit/rollback.
[ ] Funciona en tema claro.
[ ] Funciona en tema oscuro.
[ ] Se ve profesional.
[ ] No se ve como app escolar.
```

---

## 12. Fase 7 — Pulido profesional

Aplicar revisión visual final:

```text
- Jerarquía visual clara.
- Espaciado consistente.
- Cards con separación uniforme.
- Íconos del mismo tamaño.
- Estados vacíos profesionales.
- Loading states.
- Tooltips útiles.
- Mensajes de error claros.
- Diálogos compactos.
- Tablas legibles.
- KPI bar no saturada.
- Colores semánticos consistentes.
- Gráficas legibles.
- Pantallas sin saturación visual.
```

Criterio visual:

```text
La aplicación debe parecer un ERP/POS profesional para operación real de negocio, no una maqueta escolar.
```

---

## 13. Tests obligatorios

Ejecutar:

```bash
cd pos_spj_v13.4
python -m compileall .
python -m pytest tests/architecture -q
python -m pytest tests/unit -q
```

Crear o actualizar:

```text
tests/architecture/test_no_sql_in_frontend.py
tests/architecture/test_no_commit_rollback_in_frontend.py
tests/architecture/test_no_hardcoded_ui_colors.py
tests/architecture/test_ui_uses_standard_components.py
tests/architecture/test_charts_are_html_js.py
tests/architecture/test_no_native_pyqt_charts.py
tests/architecture/test_no_direct_qpushbutton_in_modules.py
tests/architecture/test_no_direct_qtablewidget_in_modules.py
tests/architecture/test_modules_are_in_target_structure.py
tests/architecture/test_no_new_logic_in_legacy_modules.py
tests/architecture/test_frontend_does_not_import_repositories.py
tests/architecture/test_frontend_does_not_import_db_connection.py
tests/architecture/test_legacy_wrappers_are_thin.py
```

---

## 14. Validación manual obligatoria

Probar manualmente:

```text
[ ] Arranque limpio con DB nueva.
[ ] Tema oscuro.
[ ] Tema claro.
[ ] Cambio de tema en caliente.
[ ] Dashboard / BI.
[ ] Ventas.
[ ] Productos.
[ ] Inventario.
[ ] Compras.
[ ] Transferencias.
[ ] Caja.
[ ] Clientes.
[ ] Diálogos.
[ ] Tablas con textos largos.
[ ] KPI bars.
[ ] Gráficas HTML + JavaScript.
[ ] Ventana maximizada.
[ ] Ventana reducida.
[ ] Navegación desde estructura nueva.
[ ] Wrappers legacy funcionando solo como puente temporal.
```

---

## 15. Orden recomendado de commits

```text
1. test: add ui architecture guardrails
2. docs: add ui ux architecture skill
3. refactor(structure): create frontend desktop target folders
4. refactor(ui): centralize visual tokens and qss variants
5. refactor(ui): create canonical frontend components
6. refactor(ui): unify kpi card and kpi bar
7. refactor(ui): add standard table policy
8. refactor(charts): add html javascript chart view
9. refactor(settings): move theme persistence out of pyqt
10. refactor(dashboard): relocate dashboard to frontend desktop modules
11. refactor(products): relocate products module to target architecture
12. refactor(inventory): relocate inventory module to target architecture
13. refactor(purchases): relocate purchases module to target architecture
14. chore(dev-db): document clean reset workflow
15. test: enforce no new ui hardcodes
16. test: enforce module relocation rules
```

---

## 16. Definición de terminado

El refactor UI/UX + arquitectura se considera terminado cuando:

```text
[ ] No hay SQL en UI.
[ ] No hay commit/rollback en UI.
[ ] No hay schema changes desde UI.
[ ] No hay colores hardcodeados en pantallas.
[ ] No hay botones fuera de factories.
[ ] No hay KPIs fuera del componente canónico.
[ ] No hay tablas fuera de StandardTable.
[ ] No hay gráficas PyQt nativas.
[ ] Todas las gráficas usan HTML + JavaScript.
[ ] Tema claro/oscuro funciona globalmente.
[ ] Los textos de tablas son visibles.
[ ] Los layouts no se sobreponen.
[ ] Los diálogos son consistentes.
[ ] La app arranca con base limpia.
[ ] No existen migraciones de rescate para desarrollo.
[ ] Se ejecutaron tests de arquitectura.
[ ] Se hizo validación manual por pantalla.
[ ] Los módulos principales viven en frontend/desktop/modules/.
[ ] Los componentes compartidos viven en frontend/desktop/components/.
[ ] Los temas viven en frontend/desktop/themes/.
[ ] Las gráficas viven en frontend/desktop/charts/.
[ ] Las lecturas viven en backend/application/queries/.
[ ] Las mutaciones viven en backend/application/use_cases/.
[ ] Los DTOs viven en backend/application/dto/.
[ ] Las reglas de negocio viven en backend/domain/.
[ ] La persistencia vive en backend/infrastructure/db/repositories/.
[ ] modulos/ ya no contiene lógica funcional principal.
[ ] interfaz/ ya no contiene pantallas principales.
[ ] ui/ ya no contiene componentes nuevos.
[ ] services/ y repositories/ legacy ya no reciben lógica nueva.
[ ] La app arranca desde la nueva estructura.
[ ] Los wrappers legacy fueron eliminados o quedan justificados temporalmente.
```

---

## 17. Principio final

```text
Una sola fuente visual.
Una sola ruta arquitectónica.
Una sola estructura objetivo.
Una sola experiencia profesional.
```

La UI no debe parecer construida pantalla por pantalla.

Debe parecer un sistema completo, coherente, empresarial y mantenible.

No basta con mejorar cómo se ve.

Debe quedar ubicado donde arquitectónicamente pertenece.
