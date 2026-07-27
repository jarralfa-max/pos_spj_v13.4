
# config.py
import os
import sqlite3
from modulos.qss_builder import build_themes

# --- Rutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(BASE_DIR, "recursos", "icons")
DATABASE_NAME = "punto_venta.db"

# ═══════════════════════════════════════════════════════════════════════════════
#  SISTEMA DE DISEÑO SPJ POS v13.4 — Modern SaaS UI (Stripe/Notion/Linear style)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  COLORES PRINCIPALES:
#  • Primario: #2563EB (azul) → Hover: #E600E6 (magenta) → Active: #CC00CC
#  • Éxito: #16A34A (verde)
#  • Error: #DC2626 (rojo)
#  • Advertencia: #D97706 (ámbar)
#  • Acento: #7C3AED (violeta)
#
#  HOVER EFFECTS:
#  • Usar variantes de #FF00FF para interacción (hover, focus, glow)
#  • Solo en elementos interactivos, nunca como fondo principal
#
#  SIDEBAR (SIEMPRE OSCURO):
#  • Fondo: #020617 | Hover: #1E293B | Activo: #2563EB
#
# ═══════════════════════════════════════════════════════════════════════════════

TEMAS = build_themes()  # ← Generado desde modulos/design_tokens.Colors
                        #   Ver modulos/qss_builder.py

# --- Rutas y configuración adicional ---
