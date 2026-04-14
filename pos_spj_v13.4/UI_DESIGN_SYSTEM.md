# 🎨 Sistema de Diseño SPJ POS v13.4

## Descripción General

Rediseño completo de la interfaz de usuario del sistema SPJ POS siguiendo principios de diseño modernos tipo SaaS (Stripe, Notion, Linear). Este documento describe los cambios implementados y cómo utilizar el nuevo sistema de diseño.

---

## 📋 Cambios Realizados

### 1. **config.py** - Sistema de Temas Rediseñado

#### Tema Oscuro (`"Oscuro"`)
- **Fondo principal**: `#0F172A` (Slate 900)
- **Cards/Superficies**: `#1E293B` (Slate 800)
- **Bordes**: `#334155` (Slate 700)
- **Texto principal**: `#F1F5F9` (Slate 100)
- **Texto secundario**: `#94A3B8` (Slate 400)

#### Tema Claro (`"Claro"`)
- **Fondo principal**: `#F8FAFC` (Slate 50)
- **Cards/Superficies**: `#FFFFFF` (Blanco)
- **Bordes**: `#E2E8F0` (Slate 200)
- **Texto principal**: `#0F172A` (Slate 900)
- **Texto secundario**: `#64748B` (Slate 500)

#### Colores de Botones Estandarizados

| Tipo | Base | Hover | Active |
|------|------|-------|--------|
| Primario | `#2563EB` | `#E600E6` | `#CC00CC` |
| Éxito | `#16A34A` | `#22C55E` | `#15803D` |
| Peligro | `#DC2626` | `#EF4444` | `#B91C1C` |
| Advertencia | `#D97706` | `#F59E0B` | `#B45309` |
| Outline | Transparente | `rgba(37,99,235,0.08)` | - |

#### Componentes UI Mejorados

- ✅ **Botones**: 5 variantes con estados hover/pressed/disabled
- ✅ **Inputs**: Focus con borde magenta `#E600E6`
- ✅ **Tablas**: Headers uppercase, hover en filas, bordes sutiles
- ✅ **Tabs**: Bordes redondeados, indicador de selección claro
- ✅ **Combobox**: Dropdown moderno con items espaciados
- ✅ **Scrollbars**: Más anchas, colores consistentes
- ✅ **Progress Bars**: Gradiente azul→magenta
- ✅ **Checkbox/Radio**: Indicadores grandes y claros
- ✅ **Cards**: Sombras suaves, bordes redondeados 12px

---

### 2. **menu_lateral.py** - Sidebar Rediseñado

#### Características del Nuevo Sidebar

```python
# Colores aplicados:
- Fondo: #020617 (Slate 950) - SIEMPRE OSCURO
- Hover items: #1E293B (Slate 800)
- Activo/Seleccionado: #2563EB (Azul primario)
- Texto normal: #94A3B8 (Slate 400)
- Texto hover: #E2E8F0 (Slate 200)
- Iconos: #94A3B8 (Slate 400)
```

#### Mejoras Implementadas

1. **Logo más grande** (28px vs 24px)
2. **Versión con color azul** (#2563EB) en lugar de cyan
3. **Espaciado mejorado** entre elementos
4. **Bordes sutiles** para separar secciones
5. **Border-radius consistente** (8px en botones)
6. **Sección logout diferenciada** con borde superior

---

## 🚀 Cómo Usar el Nuevo Sistema

### Botones Estilizados

```python
from PyQt5.QtWidgets import QPushButton

# Método 1: Usando objectName
btn = QPushButton("Guardar")
btn.setObjectName("primaryBtn")  # Azul → Magenta hover

btn2 = QPushButton("Cancelar")
btn2.setObjectName("dangerBtn")  # Rojo

btn3 = QPushButton("Editar")
btn3.setObjectName("warningBtn")  # Naranja

btn4 = QPushButton("Volver")
btn4.setObjectName("secondaryBtn")  # Gris

btn5 = QPushButton("Ver Detalles")
btn5.setObjectName("outlineBtn")  # Borde azul
```

```python
# Método 2: Usando propiedades CSS
btn = QPushButton("Aceptar")
btn.setProperty("variant", "success")
btn.style().unpolish(btn)
btn.style().polish(btn)
```

### Labels con Jerarquía Visual

```python
# Títulos principales
lbl_heading = QLabel("Ventas del Día")
lbl_heading.setObjectName("heading")  # 24px, bold

# Subtítulos
lbl_sub = QLabel("Resumen de transacciones")
lbl_sub.setObjectName("subheading")  # 16px, semibold

# Texto secundario
lbl_caption = QLabel("Actualizado hace 5 min")
lbl_caption.setObjectName("caption")  # 12px, muted
```

### Cards/Contenedores

```python
from PyQt5.QtWidgets import QFrame

card = QFrame()
card.setObjectName("card")
# O para efecto hover:
card.setProperty("variant", "card-hover")
```

### Inputs con Focus Moderno

Los inputs automáticamente tendrán:
- Borde `#334155` (oscuro) o `#E2E8F0` (claro)
- Focus: Borde magenta `#E600E6` de 2px
- Border-radius: 8px
- Padding: 10px 14px

```python
from PyQt5.QtWidgets import QLineEdit

input = QLineEdit()
input.setPlaceholderText("Buscar producto...")
# El estilo se aplica automáticamente desde el tema
```

---

## 🎯 Principios de Diseño Aplicados

### 1. **Jerarquía Visual Clara**
- Títulos grandes y bold
- Texto secundario en colores muted
- Espaciado consistente entre elementos

### 2. **Feedback Interactivo**
- Hover states en todos los elementos interactivos
- Transiciones suaves de color
- Focus visible en inputs (magenta)

### 3. **Consistencia Global**
- Mismo border-radius (8px estándar, 12px en cards)
- Paleta de colores unificada
- Tipografía consistente (Segoe UI, Inter, Roboto)

### 4. **Accesibilidad**
- Contraste suficiente entre texto y fondo
- Estados disabled claramente diferenciados
- Tamaño mínimo de 40px en botones

### 5. **Sidebar Siempre Oscuro**
- Independiente del tema seleccionado
- Máximo contraste para navegación
- Color `#020617` (más oscuro que el tema oscuro normal)

---

## 📊 Comparación Antes/Después

| Elemento | Antes | Después |
|----------|-------|---------|
| Font-size base | 11px | 13px |
| Botón height | 35px | 40px |
| Border-radius | 4-5px | 8px (12px cards) |
| Input padding | 6px 10px | 10px 14px |
| Scrollbar width | 10px | 12px |
| Header tabs padding | 8px 16px | 10px 20px |

---

## 🔧 Personalización

### Agregar Nuevas Variantes de Botón

En `config.py`, dentro de cada tema:

```css
QPushButton#customBtn, QPushButton[variant="custom"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #TU_COLOR, stop:1 #TU_COLOR_OSCURO);
    color: #FFFFFF;
    border: 1px solid #TU_COLOR_CLARO;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
    min-height: 40px;
}
QPushButton#customBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #TU_COLOR_HOVER, stop:1 #TU_COLOR_HOVER_OSCURO);
    border: 1px solid #TU_COLOR_GLOW;
}
```

### Modificar Colores del Sidebar

En `menu_lateral.py`:

```python
self.setStyleSheet("""
    QFrame#MenuLateral {
        background-color: #TU_COLOR_FONDO;
        border-right: 1px solid #TU_COLOR_BORDER;
    }
    QPushButton:hover {
        background-color: #TU_COLOR_HOVER;
    }
    QPushButton:checked {
        background-color: #TU_COLOR_ACTIVO;
    }
""")
```

---

## 📝 Notas Importantes

1. **No modificar lógica de negocio**: Todos los cambios son exclusivamente visuales
2. **Variables globales**: Usar siempre los colores definidos, no hardcodear
3. **Hover effects**: Solo usar magenta (#FF00FF variants) en hover/focus
4. **Sidebar**: Mantener siempre oscuro independientemente del tema
5. **Escalabilidad**: El sistema está diseñado para crecer con nuevos módulos

---

## 🎨 Referencias de Diseño

- **Stripe**: Limpieza visual, jerarquía clara
- **Notion**: Minimalismo, enfoque en contenido
- **Linear**: Interacciones modernas, feedback visual
- **Tailwind CSS**: Sistema de colores Slate/Zinc

---

## ✅ Checklist de Implementación

- [x] Tema oscuro actualizado con paleta Slate
- [x] Tema claro actualizado con paleta Slate
- [x] 5 variantes de botones (primary, success, danger, warning, outline)
- [x] Inputs con focus magenta
- [x] Tablas con headers uppercase y hover
- [x] Tabs con diseño moderno
- [x] Combobox con dropdown estilizado
- [x] Scrollbars personalizadas
- [x] Progress bars con gradiente
- [x] Checkbox y radio buttons modernos
- [x] Sidebar siempre oscuro (#020617)
- [x] Logo y versión actualizados
- [x] Documentación completa

---

**Versión**: 13.4  
**Fecha**: 2024  
**Autor**: SPJ POS Design Team
