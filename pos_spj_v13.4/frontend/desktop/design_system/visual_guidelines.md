# Guías visuales — SPJ Design System (JUANIS)

## Identidad de marca

| Color | Hex | Uso principal | Evitar |
|---|---|---|---|
| Verde Bosque | `#1F3B2E` | Primario, navegación activa, foco, selección | — |
| Rojo Tradicional | `#A52E2A` | Errores, acciones destructivas | Decoración frecuente |
| Dorado Premium | `#C7A254` | Acentos, KPI destacados, separadores | Grandes superficies con texto de bajo contraste |
| Crema Suave | `#F2E6CF` | Fondos cálidos, paneles suaves | Reducir legibilidad de tablas densas |
| Café Tierra | `#6B4A2E` | Bordes cálidos, texto secundario, iconos neutros | — |

La marca define la **identidad**; los **tokens semánticos** definen el
**significado**. Un color nunca se aprueba solo por ser de marca: debe cumplir
contraste (ver `tests/architecture/test_theme_contrast.py`).

## Tokens

- Color: `frontend/desktop/themes/semantic_colors.py` (`Light` / `Dark`).
- Números visuales (spacing, radii, tamaños, métricas): `themes/tokens.py`.
- QSS global: `themes/qss_builder.py`. Autoridad de tema: `themes/theme_manager.py`.

## Reglas

- Sin colores literales ni `setStyleSheet` con color en páginas/componentes.
- Estilo por `objectName` + `property("variant"|"state"|"cardVariant")`.
- El color nunca es el único indicador (texto/icono acompañan).
- Tema claro y oscuro siempre; contraste AA (texto 4.5:1, grande/UI 3.0:1).

## Jerarquía de página

```
PageHeader → (ContextBar) → (KPIBar) → (DashboardGrid) → FilterBar/Toolbar
→ contenido → paginación/acciones
```

KPIs y gráficas solo cuando respondan una necesidad operativa real.
