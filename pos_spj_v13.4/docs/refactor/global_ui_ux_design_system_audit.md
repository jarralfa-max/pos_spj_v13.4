# FASE DS-0 — Auditoría global del sistema visual SPJ ERP/POS

> Auditoría previa a la construcción del Design System global. Principio rector:
> **primero se construye el estándar, después se migran los módulos.**
> No se inventa un estándar sin revisar antes los contratos, helpers, wrappers,
> tests y componentes existentes.

Fecha de auditoría inicial: 2026-07-17.

---

## 1. Estado actual (medido)

| Métrica | Valor medido | Implicación |
|---|---|---|
| Archivos en `modulos/` con `setStyleSheet(...)` | **39** | Estilo inline disperso; migrar a QSS global por `objectName`/`property`. |
| Ocurrencias de color hex en `modulos/` | **278** | Colores hardcodeados; deben salir de tokens/tema. |
| Factories/clases KPI duplicadas | `ui_components.create_kpi_card/create_stat_card/create_kpi_bar`, `modulos/kpi_card.py`, `compras_pro.py`, `fidelidad_config.py`, + 2 `_page_base` (finance/hr usan `create_kpi_bar`) | Consolidar en `KPICard`/`KPIBar` canónicos. |
| `PageHeader` | Única definición en `modulos/ui_components.py` | Buen punto de partida: mover a `frontend/desktop/components/page_header.py` y ampliar contrato. |
| Gráficas PyQt nativas (`QChart`/matplotlib/pyqtgraph) | **1** archivo | Migrar a HTML+JS (ECharts). |
| Formatters de dinero repetidos (`f"${...:,.2f}"`) | **61** ocurrencias | Centralizar en `MoneyFormatter`. |
| Fuentes visuales legacy | `modulos/design_tokens.py` (442 L), `modulos/qss_builder.py`, `ui/themes/theme_engine.py` | Tres fuentes de verdad → consolidar en `frontend/desktop/themes/`. |

### Paleta legacy detectada (NO es la identidad de marca)

`modulos/design_tokens.py` usa una paleta genérica azul/slate (estilo Tailwind):

```
PRIMARY  #2563EB (azul)     SUCCESS #16A34A     DANGER #DC2626
WARNING  #D97706            INFO    #0891B2     ACCENT  #7C3AED (morado)
NEUTRAL  slate 50..900
```

Esta paleta **no** corresponde a la identidad **JUANIS** (Verde Bosque / Rojo
Tradicional / Dorado Premium / Crema Suave / Café Tierra). El Design System debe
nacer con la paleta JUANIS como identidad oficial (FASE DS-1).

---

## 2. Componentes existentes reutilizables (contratos protegidos)

Ya viven en `frontend/desktop/components/` y deben conservar su contrato:

| Componente | Archivo | Estado |
|---|---|---|
| `PhoneInput` (delega en `PhoneWidget`) | `phone_input.py` | Conservar contrato (`set_phone`/`get_e164`). |
| Dirección con geocoding | `address_input.py` | Conservar `GeocodingService`, providers, request_id, modo manual. |
| `PercentInput` | `percent_input.py` | Conservar (Decimal, ratio vs %). |
| `IntegerInput` | `integer_input.py` | Conservar. |
| `MoneyInput` | `money_input.py` | Conservar (Decimal + currency). |
| `QuantityInput` | `quantity_input.py` | Conservar (amount + unit). |
| `NumericInput` | `numeric_input.py` | Base numérica. |
| `StandardTable` | `tables.py` | Política de tabla canónica ya creada (HR/finance la usan). |
| `StatusBadge` | `status_badge.py` | Conservar; alinear variantes semánticas. |
| `SearchSelector` + search boxes | `search_selector.py`, `*_search_box.py` | Base para `EntitySearchInput`/`SearchableComboBox`. |
| `DateRangeFilter` | `date_range_filter.py` | Base para `FilterBar`. |

### Primitivos que aún viven en legacy (`modulos/ui_components.py`)

`PageHeader`, `create_kpi_bar`, `create_*_button`, `create_card`, `create_kpi_card`,
`create_stat_card`, `create_table_button`, dialog button normalizer. Estos son los
consumidores actuales de finance/hr (`_page_base` importa de `modulos.ui_components`).
Deben migrarse a `frontend/desktop/components/` conservando el contrato y dejando
wrappers temporales hasta migrar todos los imports.

---

## 3. Duplicados y fragmentación detectados

```
[ KPI ]        create_kpi_card / create_stat_card / kpi_card.py / compras_pro / fidelidad_config
[ Cards ]      create_card + QFrame/QGroupBox estilizados por módulo
[ Headers ]    PageHeader (único) + headers manuales por pantalla
[ Tooltips ]   apply_tooltip / apply_spj_tooltips + setToolTip directo (múltiples módulos)
[ Colores ]    design_tokens.py + qss_builder.py + 278 hex inline
[ Temas ]      modulos/qss_builder.py + ui/themes/theme_engine.py
[ Formatters ] 61 f-strings de dinero + formateos de cantidad/porcentaje ad hoc
[ Charts ]     1 gráfica PyQt nativa
[ Inputs ]     horarios/tiempos capturados con QLineEdit (p. ej. Configuración)
```

---

## 4. Brechas contra el estándar objetivo

Faltan por completo (a crear en DS-1..DS-6):

```
frontend/desktop/themes/       (brand_palette, semantic_colors, tokens, qss_builder, theme_manager)
frontend/desktop/charts/       (chart_bridge, templates, renderers ECharts)
frontend/desktop/formatters/   (money, quantity, percentage, phone, address, date, time, duration, status)
frontend/desktop/i18n/         (es_mx)
frontend/desktop/design_system/(catalog, contracts, gallery, guidelines, migration_guide)
```

Componentes faltantes en `components/`: `buttons`, `page_header`, `section_header`,
`toolbar`, `filter_bar`, `cards`, `kpi_card`, `kpi_bar`, `dialogs`, `tooltip`, `icons`,
`chart_view`, `dashboard_grid`, estados (`loading/empty/error/permission/offline/stale/partial`),
inputs especializados (`email`, `tax_identifier`, `decimal`, `time`, `time_range`,
`month`, `duration`, `search`, `searchable_combo`, `entity_search`, `barcode`,
`password`, `file_path`, `datetime`, `date`), `form_field`, `standard_form`.

---

## 5. Riesgos de la migración

1. **Doble fuente de verdad temporal**: `modulos/design_tokens.py` y el nuevo
   `frontend/desktop/themes/tokens.py` coexistirán durante la transición. El nuevo
   layer es **aditivo**; el legacy no se elimina hasta migrar todos los consumidores.
2. **Contratos protegidos por tests** (PhoneWidget, AddressAutocomplete, TimeInput
   objetivo): reemplazos incompatibles romperían tests. Se conservan vía wrappers.
3. **Contraste**: la paleta JUANIS (dorado/crema) exige validación de contraste
   AA; no se aprueba un color solo por pertenecer a la marca.

---

## 6. Plan de ejecución (orden de dependencias)

```
DS-0  Auditoría (este documento)                         ← ENTREGADO
DS-1  Identidad JUANIS: brand_palette + semantic_colors + contraste + tests
DS-2  Tokens + qss_builder + theme_manager
DS-3  Componentes base (icons, buttons, page_header, cards, kpi, tables, dialogs, tooltip, estados)
DS-4  Inputs especializados (time, time_range, email, tax_id, decimal, ...)
DS-5  Charts (ChartDataDTO, HtmlChartView, ECharts, ChartCard, DashboardGrid)
DS-6  Formatters + i18n
DS-7  Component gallery
DS-8  Guardrails de arquitectura
DS-9  Migración piloto: Configuración
DS-10 Plantilla de migración por módulo
DS-11 Validación final
```

Estado global del Design System: **IN_PROGRESS** (fundación DS-1/DS-2 en construcción).
