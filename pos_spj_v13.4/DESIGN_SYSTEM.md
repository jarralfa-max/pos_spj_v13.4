# SPJ POS v13.4 — Design System Documentation

## 📋 Índice

1. [Introducción](#introducción)
2. [Design Tokens](#design-tokens)
3. [Colores](#colores)
4. [Tipografía](#tipografía)
5. [Componentes](#componentes)
6. [Buenas Prácticas](#buenas-prácticas)
7. [Migración](#migración)

---

## 🎯 Introducción

El **Design System de SPJ POS v13.4** es un conjunto de estándares visuales y componentes reutilizables que garantizan consistencia en toda la aplicación. Está inspirado en sistemas modernos tipo SaaS (Stripe, Notion, Linear).

### Objetivos

- ✅ Consistencia visual en todos los módulos
- ✅ Reducción de deuda técnica UI
- ✅ Mejora de experiencia de usuario
- ✅ Soporte completo para temas claro/oscuro
- ✅ Código mantenible y escalable

---

## 🎨 Design Tokens

Los design tokens son las variables fundamentales del sistema de diseño.

### Archivos Clave

| Archivo | Propósito |
|---------|-----------|
| `modulos/design_tokens.py` | Variables de colores, espaciado, tipografía |
| `modulos/ui_components.py` | Componentes factory reutilizables |
| `config.py` | Temas QSS globales (Claro/Oscuro) |

### Uso Básico

```python
from modulos.design_tokens import Colors, Spacing, Typography, Borders

# Colores
primary = Colors.PRIMARY_BASE      # #2563EB
hover = Colors.PRIMARY_HOVER       # #E600E6

# Espaciado
padding = Spacing.MD               # 12px

# Tipografía
font_size = Typography.SIZE_SM     # 13px

# Bordes
radius = Borders.RADIUS_LG         # 8px
```

---

## 🌈 Colores

### Paleta Principal

| Tipo | Base | Hover | Active | BG Soft |
|------|------|-------|--------|---------|
| **Primario** | `#2563EB` | `#E600E6` | `#CC00CC` | `#DBEAFE` |
| **Éxito** | `#16A34A` | `#22C55E` | `#15803D` | `#DCFCE7` |
| **Peligro** | `#DC2626` | `#EF4444` | `#B91C1C` | `#FEE2E2` |
| **Advertencia** | `#D97706` | `#F59E0B` | `#B45309` | `#FEF3C7` |
| **Info** | `#0891B2` | `#06B6D4` | `#0E7490` | `#ECFEFF` |
| **Acento** | `#7C3AED` | `#8B5CF6` | `#6D28D9` | `#F5F3FF` |

### Neutrales (Slate)

| Nombre | Claro | Oscuro |
|--------|-------|--------|
| Background | `#F8FAFC` | `#0F172A` |
| Card | `#FFFFFF` | `#1E293B` |
| Border | `#E2E8F0` | `#334155` |
| Text Primary | `#0F172A` | `#F1F5F9` |
| Text Secondary | `#64748B` | `#94A3B8` |

### Sidebar (SIEMPRE OSCURO)

| Elemento | Color |
|----------|-------|
| Fondo | `#020617` |
| Hover | `#1E293B` |
| Activo | `#2563EB` |
| Texto | `#E2E8F0` |
| Íconos | `#94A3B8` |

### Reglas de Uso

✅ **CORRECTO:**
```python
# Usar variable del sistema
btn.setStyleSheet(f"background: {Colors.PRIMARY.BASE};")
```

❌ **INCORRECTO:**
```python
# Hardcodear colores
btn.setStyleSheet("background: #2563EB;")
```

---

## 📐 Espaciado

Sistema basado en múltiplos de 4px (grid de 8px).

| Token | Valor | Uso |
|-------|-------|-----|
| `Spacing.XS` | 4px | Mínimo, gaps pequeños |
| `Spacing.SM` | 8px | Base, padding interno |
| `Spacing.MD` | 12px | Estándar, entre elementos |
| `Spacing.LG` | 16px | Amplio, secciones |
| `Spacing.XL` | 24px | Extra amplio, containers |
| `Spacing.XXL` | 32px | Separación grande |

### Botones

```python
# Dimensiones estándar
Height: 36-40px
Padding: 6px 12px
```

### Inputs

```python
# Mismo height que botones
Height: 36px
Padding: 6px 12px
```

---

## 🔤 Tipografía

### Familia

```python
Typography.FONT_FAMILY = "'Segoe UI', 'Inter', 'Roboto', sans-serif"
```

### Tamaños

| Token | Valor | Uso |
|-------|-------|-----|
| `SIZE_XS` | 11px | Captions, badges |
| `SIZE_SM` | 13px | Botones, inputs |
| `SIZE_MD` | 14px | Texto base |
| `SIZE_LG` | 16px | Subtítulos |
| `SIZE_XL` | 20px | Títulos sección |
| `SIZE_XXL` | 24px | Títulos principales |

### Pesos

- Normal: 400
- Medium: 500
- Semibold: 600
- Bold: 700

---

## 🧩 Componentes

### Botones

#### Factory Functions

```python
from modulos.ui_components import (
    create_primary_button,
    create_success_button,
    create_danger_button,
    create_secondary_button,
    create_outline_button,
)

# Uso
btn = create_primary_button(
    parent=self,
    text="Guardar",
    tooltip="Guardar cambios del pedido"
)
```

#### Tipos

| Tipo | ObjectName | Uso |
|------|------------|-----|
| Primario | `primaryBtn` | Acciones principales |
| Secundario | `secondaryBtn` | Acciones secundarias |
| Éxito | `successBtn` | Guardar, confirmar |
| Peligro | `dangerBtn` | Eliminar, cancelar |
| Advertencia | `warningBtn` | Editar, ajustar |
| Outline | `outlineBtn` | Menos prominente |

#### Hover Effects

Todos los botones usan variantes magenta en hover:
- Hover: `#E600E6`
- Active: `#CC00CC`
- Glow: `#FF4DFF`

### Cards

```python
from modulos.ui_components import create_card, create_stat_card

# Card contenedora
card = create_card(parent, padding=Spacing.LG)

# Stat card para dashboard
stat = create_stat_card(
    parent=self,
    title="Ventas Hoy",
    value="$12,450",
    color_variant="success"
)
```

**Regla importante:** Cards con fondo neutro, color solo en indicadores.

### Badges

```python
from modulos.ui_components import create_badge

badge = create_badge(
    parent=self,
    text="Completado",
    variant="success"  # primary, success, danger, warning, info, neutral
)
```

### Tooltips

```python
from modulos.ui_components import apply_tooltip

apply_tooltip(button, "Guardar cambios del pedido", delay_ms=300)
```

**Estilo global (config.py):**
- Fondo: `#1E293B` (oscuro) / `#0F172A` (claro)
- Texto: `#F1F5F9` / `#E2E8F0`
- Border-radius: 6px
- Padding: 6px 10px
- Shadow: `0 4px 12px rgba(0,0,0,0.15)`

### Labels con Jerarquía

```python
from modulos.ui_components import (
    create_heading,      # 24px bold
    create_subheading,   # 16px semibold
    create_caption,      # 11px regular
)

titulo = create_heading(self, "Ventas del Día")
subtitulo = create_subheading(self, "Resumen diario")
nota = create_caption(self, "Actualizado hace 5 min")
```

---

## 📦 Temas

### Modo Claro

```python
Background: #F8FAFC
Card: #FFFFFF
Border: #E2E8F0
Text: #0F172A
```

### Modo Oscuro

```python
Background: #0F172A
Card: #1E293B
Border: #334155
Text: #F1F5F9
```

### Aplicar Tema

```python
from ui.themes.theme_engine import apply_theme

apply_theme(widget, "Oscuro")  # o "Claro"
```

---

## ✅ Buenas Prácticas

### DO ✅

1. **Usar design tokens siempre**
   ```python
   from modulos.design_tokens import Colors
   color = Colors.PRIMARY_BASE
   ```

2. **Usar factory functions para componentes**
   ```python
   from modulos.ui_components import create_primary_button
   btn = create_primary_button(self, "Guardar", "Guardar pedido")
   ```

3. **Asignar objectName para estilos CSS**
   ```python
   btn.setObjectName("primaryBtn")
   ```

4. **Agregar tooltips descriptivos**
   ```python
   # Explicar acción, no repetir label
   apply_tooltip(btn, "Guardar cambios del pedido")
   ```

5. **Usar cards con fondo neutro**
   ```python
   # Color solo en iconos/indicadores
   card = create_card(parent)
   ```

6. **Mantener spacing consistente**
   ```python
   layout.setSpacing(Spacing.MD)  # 12px
   ```

### DON'T ❌

1. **No hardcodear colores**
   ```python
   # MAL
   btn.setStyleSheet("background: #2563EB;")
   
   # BIEN
   btn.setStyleSheet(f"background: {Colors.PRIMARY_BASE};")
   ```

2. **No usar múltiples colores fuertes**
   ```python
   # MAL - Demasiados colores compitiendo
   card.setStyleSheet("background: red; border: blue;")
   
   # BIEN - Fondo neutro, un color de acento
   card.setStyleSheet("background: white; border-left: 4px solid #2563EB;")
   ```

3. **No crear botones grandes**
   ```python
   # MAL
   btn.setFixedHeight(50)
   
   # BIEN
   btn.setFixedHeight(Spacing.BTN_HEIGHT_MIN)  # 36px
   ```

4. **No duplicar estilos**
   ```python
   # MAL - Estilo inline repetido
   btn1.setStyleSheet("...20 líneas de CSS...")
   btn2.setStyleSheet("...20 líneas de CSS...")
   
   # BIEN - Usar objectName y CSS global
   btn1.setObjectName("primaryBtn")
   btn2.setObjectName("primaryBtn")
   ```

---

## 🔄 Migración

### Paso 1: Identificar colores hardcoded

```bash
grep -r "setStyleSheet.*#[0-9A-F]" modulos/
```

### Paso 2: Reemplazar con tokens

```python
# Antes
label.setStyleSheet("color: #2563EB;")

# Después
from modulos.design_tokens import Colors
label.setStyleSheet(f"color: {Colors.PRIMARY_BASE};")
```

### Paso 3: Usar factory components

```python
# Antes
btn = QPushButton("Guardar")
btn.setStyleSheet("""
    QPushButton {
        background: #2563EB;
        color: white;
        border-radius: 8px;
        padding: 6px 12px;
    }
""")

# Después
from modulos.ui_components import create_primary_button
btn = create_primary_button(self, "Guardar", "Guardar pedido")
```

### Paso 4: Agregar tooltips

```python
# En todos los botones con ícono o acciones críticas
from modulos.ui_components import apply_tooltip
apply_tooltip(btn, "Descripción clara de la acción")
```

---

## 📊 Métricas de Calidad

| Métrica | Objetivo | Actual |
|---------|----------|--------|
| Colores hardcoded | 0 | ~200 (en progreso) |
| Botones estandarizados | 100% | ~60% |
| Tooltips implementados | 100% | ~30% |
| Módulos migrados | 100% | ~15% |

---

## 📚 Referencias

- [design_tokens.py](../modulos/design_tokens.py) - Variables de diseño
- [ui_components.py](../modulos/ui_components.py) - Componentes factory
- [config.py](../config.py) - Temas QSS globales
- [theme_engine.py](../ui/themes/theme_engine.py) - Motor de temas

---

*Documentación actualizada: SPJ POS v13.4*
