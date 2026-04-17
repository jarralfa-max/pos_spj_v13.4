# modulos/loyalty_card_designer.py — SPJ POS v13
"""
Diseñador y generador de tarjetas de fidelidad físicas.

Layout: 24 tarjetas por hoja (12×18 pulgadas), grid 6×4
  
Pestañas:
  🎨 Diseñador — plantilla con vista previa en tiempo real
  ⚙️  QR Config — qué datos codifica cada QR
  🖨️  Generar Lote — PDF para imprenta (24 tarjetas/hoja 12×18")
  📋 Emitidas — gestión de tarjetas asignadas
  📦 Historial Lotes — registro de PDFs generados
"""
from __future__ import annotations
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.ui_components import (
    create_primary_button, create_secondary_button, create_success_button, 
    create_danger_button, create_input, create_combo, create_card,
    create_heading, create_subheading, create_caption, apply_tooltip
)
import json
import logging
import os
import uuid
from datetime import date

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QBrush, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QDialogButtonBox, QMessageBox, QFileDialog,
    QColorDialog, QTabWidget, QProgressBar, QCheckBox,
    QSpinBox, QFrame, QScrollArea, QTextEdit
)

logger = logging.getLogger("spj.loyalty_card")

CARD_W_PX = 340
CARD_H_PX = 215

NIVELES = {
    "Bronce":  {"color": "#CD7F32", "icono": "🥉"},
    "Plata":   {"color": "#A8A8A8", "icono": "🥈"},
    "Oro":     {"color": "#FFD700", "icono": "🥇"},
    "Platino": {"color": "#E5E4E2", "icono": "💎"},
    "Black":   {"color": "#374151", "icono": "⚫"},
}

PLANTILLA_DEFAULT = {
    "nombre_empresa": "CARNICERÍA SPJ",
    "eslogan": "Tu fidelidad, tu premio",
    "color_fondo": "#1a1a2e",
    "color_texto": "#ffc72c",
    "color_acento": "#e94560",
    "logo_path": "",
    "qr_incluir_id": True,
    "qr_website": "",
    "qr_facebook": "",
    "qr_instagram": "",
    "qr_tiktok": "",
    "qr_whatsapp": "",
    "qr_separador": "|",
}


# ── Vista previa ────────────────────────────────────────────────────────────

class CardPreviewRenderer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plantilla = dict(PLANTILLA_DEFAULT)
        self.nivel = "Bronce"
        self.card_id = "SPJ000001"
        self.setFixedSize(CARD_W_PX, CARD_H_PX)
        self.setAlignment(Qt.AlignCenter)
        self._render()

    def actualizar(self, plantilla: dict, nivel: str = "Bronce", card_id: str = "SPJ000001"):
        self.plantilla = plantilla
        self.nivel = nivel
        self.card_id = card_id
        self._render()

    def _render(self):
        p = self.plantilla
        pix = QPixmap(CARD_W_PX, CARD_H_PX)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        bg = QColor(p.get("color_fondo", "#1a1a2e"))
        fg = QColor(p.get("color_texto", "#ffffff"))
        acc = QColor(p.get("color_acento", "#e94560"))

        # v13.30: Background image support
        bg_img = p.get("bg_image_path", "")
        if bg_img and os.path.exists(bg_img):
            bg_pix = QPixmap(bg_img)
            if not bg_pix.isNull():
                scaled_bg = bg_pix.scaled(CARD_W_PX, CARD_H_PX,
                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(0, 0, scaled_bg)
                # Draw rounded mask
                painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
                mask = QPixmap(CARD_W_PX, CARD_H_PX)
                mask.fill(Qt.transparent)
                mp = QPainter(mask)
                mp.setBrush(QBrush(QColor("white"))); mp.setPen(Qt.NoPen)
                mp.drawRoundedRect(0, 0, CARD_W_PX, CARD_H_PX, 10, 10)
                mp.end()
                painter.drawPixmap(0, 0, mask)
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            else:
                painter.setBrush(QBrush(bg)); painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(0, 0, CARD_W_PX, CARD_H_PX, 10, 10)
        else:
            painter.setBrush(QBrush(bg)); painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, CARD_W_PX, CARD_H_PX, 10, 10)
            overlay = QLinearGradient(0, 0, CARD_W_PX, CARD_H_PX)
            overlay.setColorAt(0, QColor(255, 255, 255, 8))
            overlay.setColorAt(1, QColor(0, 0, 0, 20))
            painter.setBrush(QBrush(overlay))
            painter.drawRoundedRect(0, 0, CARD_W_PX, CARD_H_PX, 10, 10)

        # Zona izquierda: QR placeholder + ID
        left_w = int(CARD_W_PX * 0.30)
        qr_m = 8; qr_size = left_w - qr_m * 2
        painter.setBrush(QBrush(QColor("white"))); painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(qr_m, qr_m, qr_size, qr_size, 4, 4)
        self._draw_qr_placeholder(painter, qr_m + 4, qr_m + 4, qr_size - 8, QColor("#1a1a1a"))
        painter.setPen(QPen(QColor(255, 255, 255, 180)))
        painter.setFont(QFont("Courier New", 7, QFont.Bold))
        painter.drawText(0, qr_m + qr_size + 6, left_w, 16, Qt.AlignCenter, self.card_id[:10])

        # Separador
        painter.setPen(QPen(QColor(255, 255, 255, 40)))
        painter.drawLine(left_w + 2, 12, left_w + 2, CARD_H_PX - 12)

        # Zona central: texto
        cx = left_w + 10
        painter.setPen(QPen(fg))
        painter.setFont(QFont("Arial", 11, QFont.Bold))
        painter.drawText(cx, 18, CARD_W_PX - left_w - 10, 22,
                         Qt.AlignLeft | Qt.AlignVCenter,
                         p.get("nombre_empresa", "NEGOCIO")[:35])
        painter.setFont(QFont("Arial", 8)); painter.setPen(QPen(acc))
        painter.drawText(cx, 44, CARD_W_PX - left_w - 70, 18,
                         Qt.AlignLeft, "Tarjeta de Fidelidad")

        nivel_cfg = NIVELES.get(self.nivel, NIVELES["Bronce"])
        painter.setBrush(QBrush(acc)); painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(cx, 66, 80, 18, 4, 4)
        painter.setPen(QPen(QColor("white")))
        painter.setFont(QFont("Arial", 7, QFont.Bold))
        painter.drawText(cx, 66, 80, 18, Qt.AlignCenter,
                         f"{nivel_cfg['icono']} {self.nivel}")

        eslogan = p.get("eslogan", "")[:60]  # v13.30: increased from 35
        painter.setPen(QPen(QColor(255, 255, 255, 160)))
        painter.setFont(QFont("Arial", 7, italic=True))
        painter.drawText(cx, CARD_H_PX - 28, CARD_W_PX - left_w - 10, 20,
                         Qt.AlignLeft | Qt.TextWordWrap, f'"{eslogan}"')

        # Zona derecha: logo
        right_x = int(CARD_W_PX * 0.75); right_w = CARD_W_PX - right_x - 6
        logo_path = p.get("logo_path", "")
        if logo_path and os.path.exists(logo_path):
            logo_pix = QPixmap(logo_path)
            if not logo_pix.isNull():
                scaled = logo_pix.scaled(right_w, right_w, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
                painter.drawPixmap(right_x, (CARD_H_PX - scaled.height()) // 2, scaled)
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 20)))
            painter.setPen(QPen(QColor(255, 255, 255, 50)))
            painter.drawRoundedRect(right_x, (CARD_H_PX - right_w) // 2,
                                    right_w, right_w, 6, 6)
            painter.setPen(QPen(QColor(255, 255, 255, 80)))
            painter.setFont(QFont("Arial", 7))
            painter.drawText(right_x, (CARD_H_PX - right_w) // 2,
                             right_w, right_w, Qt.AlignCenter, "LOGO")
        painter.end()
        self.setPixmap(pix)

    def _draw_qr_placeholder(self, painter, x, y, size, color):
        import hashlib
        grid = 7; cell = size / grid
        painter.setBrush(QBrush(color)); painter.setPen(Qt.NoPen)
        for cx2, cy2 in [(0, 0), (grid - 3, 0), (0, grid - 3)]:
            for row in range(3):
                for col in range(3):
                    if row in (0, 2) or col in (0, 2):
                        painter.drawRect(int(x + (cx2 + col) * cell),
                                         int(y + (cy2 + row) * cell),
                                         int(cell) + 1, int(cell) + 1)
        h = hashlib.md5(self.card_id.encode()).hexdigest()
        for row in range(grid):
            for col in range(grid):
                if h[(row * grid + col) % 32] in "02468ace":
                    painter.drawRect(int(x + col * cell), int(y + row * cell),
                                     int(cell), int(cell))


# ── Hilo generación PDF ─────────────────────────────────────────────────────

class BatchPDFWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, cards: list, plantilla: dict, output_path: str):
        super().__init__()
        self.cards = cards
        self.plantilla = plantilla
        self.output_path = output_path

    def run(self):
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import inch
            from reportlab.lib.units import mm
            from reportlab.graphics.barcode.qr import QrCodeWidget
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics import renderPDF
            from reportlab.lib.colors import HexColor, white

            # Tamaño de papel: 12 x 18 pulgadas
            pagesize = (12 * inch, 18 * inch)
            PAGE_W, PAGE_H = pagesize
            # Grid: 6 columnas x 4 filas = 24 tarjetas por hoja
            cols, rows = 6, 4
            MARGIN = 5 * mm
            GAP = 3 * mm
            CW = (PAGE_W - 2 * MARGIN - (cols - 1) * GAP) / cols
            CH = (PAGE_H - 2 * MARGIN - (rows - 1) * GAP) / rows

            p = self.plantilla

            def qr_content(card_id):
                parts = [card_id] if p.get("qr_incluir_id", True) else []
                if p.get("qr_website"):   parts.append(f"WEB:{p['qr_website']}")
                if p.get("qr_whatsapp"):  parts.append(f"WA:{p['qr_whatsapp']}")
                if p.get("qr_facebook"):  parts.append(f"FB:{p['qr_facebook']}")
                if p.get("qr_instagram"): parts.append(f"IG:{p['qr_instagram']}")
                if p.get("qr_tiktok"):    parts.append(f"TT:{p['qr_tiktok']}")
                return (p.get("qr_separador", "|")).join(parts) or card_id

            c = rl_canvas.Canvas(self.output_path, pagesize=pagesize)
            total = len(self.cards)

            def draw_card(x, y, card):
                cid = card.get("codigo", "SPJ000000")
                bg = HexColor(p.get("color_fondo", "#1a1a2e"))
                fg = HexColor(p.get("color_texto", "#ffffff"))
                acc = HexColor(p.get("color_acento", "#e94560"))

                # v13.30: Background image support
                bg_img = p.get("bg_image_path", "")
                if bg_img and os.path.exists(bg_img):
                    try:
                        c.drawImage(bg_img, x, y, CW, CH,
                                    preserveAspectRatio=False, mask="auto")
                    except Exception:
                        # Fallback to solid color
                        c.setFillColor(bg)
                        c.roundRect(x, y, CW, CH, 3 * mm, fill=1, stroke=0)
                else:
                    c.setFillColor(bg)
                    c.roundRect(x, y, CW, CH, 3 * mm, fill=1, stroke=0)

                lw = CW * 0.30; qs = lw - 6 * mm
                qx = x + 3 * mm; qy = y + (CH - qs) / 2 + 1 * mm
                qrw = QrCodeWidget(qr_content(cid))
                qrw.barWidth = qrw.barHeight = qs
                d = Drawing(qs, qs); d.add(qrw)
                c.setFillColor(white)
                c.roundRect(qx - 1*mm, qy - 1*mm, qs + 2*mm, qs + 2*mm, 1*mm, fill=1, stroke=0)
                renderPDF.draw(d, c, qx, qy)
                c.setFillColor(HexColor("#cccccc")); c.setFont("Courier", 5.0)
                c.drawCentredString(x + lw / 2, y + 3*mm, cid)
                c.setStrokeColor(HexColor("#ffffff30")); c.setLineWidth(0.4)
                c.line(x + lw, y + 4*mm, x + lw, y + CH - 4*mm)

                ctx = x + lw + 3*mm; cty = y + CH - 9*mm
                c.setFillColor(fg); c.setFont("Helvetica-Bold", 8.5)
                c.drawString(ctx, cty, p.get("nombre_empresa", "SPJ")[:35])
                c.setFillColor(acc); c.setFont("Helvetica", 6.5)
                c.drawString(ctx, cty - 7*mm, "Tarjeta de Fidelidad")

                nivel = card.get("nivel", "Bronce")
                bw = 20*mm; bh = 4.5*mm; bx = ctx; by = cty - 15*mm
                c.setFillColor(acc); c.roundRect(bx, by, bw, bh, 1*mm, fill=1, stroke=0)
                c.setFillColor(white); c.setFont("Helvetica-Bold", 5.5)
                c.drawCentredString(bx + bw/2, by + 1.2*mm, f"★ {nivel}")

                eslogan = p.get("eslogan", "")[:60]
                c.setFillColor(HexColor("#bbbbbb")); c.setFont("Helvetica-Oblique", 5.5)
                c.drawString(ctx, y + 5.5*mm, f'"{eslogan}"')

                rx = x + CW * 0.75; rw = CW * 0.21
                logo = p.get("logo_path", "")
                if logo and os.path.exists(logo):
                    try:
                        c.drawImage(logo, rx, y + (CH - rw) / 2, rw, rw,
                                    preserveAspectRatio=True, mask="auto")
                    except Exception:
                        pass

            card_idx = 0
            while card_idx < total:
                for row in range(rows):
                    for col in range(cols):
                        if card_idx >= total: break
                        px2 = MARGIN + col * (CW + GAP)
                        py2 = PAGE_H - MARGIN - (row + 1) * CH - row * GAP
                        draw_card(px2, py2, self.cards[card_idx])
                        card_idx += 1
                        self.progress.emit(card_idx, total)
                    if card_idx >= total: break
                c.setStrokeColor(HexColor("#aaaaaa")); c.setLineWidth(0.2)
                for rr in range(rows + 1):
                    yc = PAGE_H - MARGIN - rr * (CH + GAP) + GAP / 2
                    c.line(MARGIN - 3*mm, yc, PAGE_W - MARGIN + 3*mm, yc)
                for cc in range(cols + 1):
                    xc = MARGIN + cc * (CW + GAP) - GAP / 2
                    c.line(xc, MARGIN - 3*mm, xc, PAGE_H - MARGIN + 3*mm)
                if card_idx < total: c.showPage()

            c.save()
            self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))


# ── Módulo principal ────────────────────────────────────────────────────────

class ModuloLoyaltyCardDesigner(QWidget):

    def __init__(self, container=None, conexion=None, usuario="admin", parent=None):
        super().__init__(parent)
        # Support both container and legacy conexion arg
        if container and hasattr(container, 'db'):
            self.conexion = container.db
        else:
            self.conexion = conexion
        self.container = container
        self.usuario = usuario
        self.plantilla = self._load_plantilla()
        self._pdf_worker = None
        self._build_ui()
        self._init_tables()

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        pass

    def _load_plantilla(self) -> dict:
        try:
            row = self.conexion.execute(
                "SELECT valor FROM configuraciones WHERE clave='loyalty_card_plantilla'"
            ).fetchone()
            if row and row[0]:
                d = dict(PLANTILLA_DEFAULT)
                d.update(json.loads(row[0]))
                return d
        except Exception:
            pass
        return dict(PLANTILLA_DEFAULT)

    def _save_plantilla(self):
        try:
            self.conexion.execute(
                "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)",
                ("loyalty_card_plantilla", json.dumps(self.plantilla)))
            try: self.conexion.commit()
            except Exception: pass
        except Exception as e:
            logger.warning("_save_plantilla: %s", e)

    def _init_tables(self):
        """Ensure tarjetas_fidelidad has all needed columns regardless of original schema."""
        try:
            # Create table only if doesn't exist at all
            self.conexion.execute("""
                CREATE TABLE IF NOT EXISTS tarjetas_fidelidad(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_cliente INTEGER REFERENCES clientes(id),
                    codigo_qr TEXT UNIQUE,
                    nivel TEXT DEFAULT 'Bronce',
                    estado TEXT DEFAULT 'disponible',
                    puntos_actuales INTEGER DEFAULT 0,
                    es_pregenerada INTEGER DEFAULT 0,
                    fecha_creacion DATETIME DEFAULT (datetime('now')),
                    fecha_asignacion DATETIME,
                    observaciones TEXT
                )
            """)
            # Add columns that might be missing from either schema variant
            for col in [
                "codigo_qr TEXT", "codigo TEXT", "estado TEXT DEFAULT 'disponible'",
                "activa INTEGER DEFAULT 1", "puntos INTEGER DEFAULT 0",
                "puntos_actuales INTEGER DEFAULT 0", "es_pregenerada INTEGER DEFAULT 0",
                "nivel TEXT DEFAULT 'Bronce'", "notas TEXT", "observaciones TEXT",
                "fecha_emision DATE", "fecha_creacion DATETIME",
                "fecha_asignacion DATETIME", "fecha_vencimiento DATE",
                "numero TEXT",
            ]:
                try:
                    self.conexion.execute(f"ALTER TABLE tarjetas_fidelidad ADD COLUMN {col}")
                except Exception:
                    pass  # Column already exists
            # Ensure lotes PDF table exists
            self.conexion.execute("""
                CREATE TABLE IF NOT EXISTS lotes_tarjetas_pdf(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cantidad INTEGER, nivel TEXT, ruta_pdf TEXT,
                    plantilla TEXT, usuario TEXT,
                    fecha DATETIME DEFAULT (datetime('now'))
                )
            """)
            try:
                self.conexion.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tarjetas_cliente "
                    "ON tarjetas_fidelidad(id_cliente)")
            except Exception:
                pass
            try:
                self.conexion.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_init_tables: %s", e)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        hdr = QHBoxLayout()
        t = create_heading("💳 Diseñador de Tarjetas de Fidelidad")
        hdr.addWidget(t); hdr.addStretch()
        lay.addLayout(hdr)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        self.tabs.addTab(self._build_tab_disenador(), "🎨 Diseñador")
        self.tabs.addTab(self._build_tab_qr(),        "⚙️ Config QR")
        self.tabs.addTab(self._build_tab_lote(),      "🖨️ Generar Lote")
        self.tabs.addTab(self._build_tab_emitidas(),  "📋 Emitidas")
        self.tabs.addTab(self._build_tab_historial(), "📦 Historial Lotes")
        self.tabs.currentChanged.connect(self._on_tab_change)

    # ── Tab 1: Diseñador ────────────────────────────────────────────────────

    def _build_tab_disenador(self) -> QWidget:
        w = QWidget(); lay = QHBoxLayout(w)

        # Panel izquierdo: controles
        left = QWidget(); left.setMaximumWidth(300); ll = QVBoxLayout(left)

        grp_neg = QGroupBox("Negocio")
        fn = QFormLayout(grp_neg)
        self.txt_nombre_emp = QLineEdit(self.plantilla.get("nombre_empresa", ""))
        self.txt_eslogan    = QLineEdit(self.plantilla.get("eslogan", ""))
        self.txt_nombre_emp.textChanged.connect(self._on_plantilla_change)
        self.txt_eslogan.textChanged.connect(self._on_plantilla_change)
        fn.addRow("Nombre:", self.txt_nombre_emp)
        fn.addRow("Eslogan:", self.txt_eslogan)
        ll.addWidget(grp_neg)

        grp_logo = QGroupBox("Logo")
        fl = QFormLayout(grp_logo)
        self.txt_logo_path = QLineEdit(self.plantilla.get("logo_path", ""))
        self.txt_logo_path.setReadOnly(True)
        btn_logo = create_secondary_button(self, "📁 Seleccionar logo")
        apply_tooltip(btn_logo, "Seleccionar archivo de imagen para el logo")
        btn_logo.clicked.connect(self._seleccionar_logo)
        logo_row = QHBoxLayout(); logo_row.addWidget(self.txt_logo_path, 1); logo_row.addWidget(btn_logo)
        fl.addRow("Archivo:", logo_row)
        ll.addWidget(grp_logo)

        # v13.30: Fondo personalizado (imagen de plantilla)
        grp_bg = QGroupBox("Fondo de tarjeta")
        fbg = QFormLayout(grp_bg)
        self.txt_bg_path = QLineEdit(self.plantilla.get("bg_image_path", ""))
        self.txt_bg_path.setReadOnly(True)
        btn_bg = create_secondary_button(self, "📁 Cargar imagen de fondo")
        apply_tooltip(btn_bg, "Seleccionar archivo de imagen para el fondo de la tarjeta")
        btn_bg.clicked.connect(self._seleccionar_fondo)
        btn_bg_clear = create_danger_button(self, "🗑️ Limpiar fondo")
        apply_tooltip(btn_bg_clear, "Quitar imagen de fondo")
        btn_bg_clear.setFixedWidth(120)
        btn_bg_clear.clicked.connect(lambda: (
            self.txt_bg_path.clear(),
            self.plantilla.update({"bg_image_path": ""}),
            self._on_plantilla_change()))
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.txt_bg_path, 1)
        bg_row.addWidget(btn_bg)
        bg_row.addWidget(btn_bg_clear)
        fbg.addRow("Imagen:", bg_row)
        lbl_bg_tip = create_caption("Usa una imagen PNG/JPG de 856×540px (tarjeta CR80 a 100dpi)")
        fbg.addRow("", lbl_bg_tip)
        ll.addWidget(grp_bg)

        grp_col = QGroupBox("Colores")
        fc = QFormLayout(grp_col)
        self.btn_color_fondo  = self._mk_color_btn(self.plantilla.get("color_fondo","#1a1a2e"), "color_fondo")
        self.btn_color_texto  = self._mk_color_btn(self.plantilla.get("color_texto","#ffffff"), "color_texto")
        self.btn_color_acento = self._mk_color_btn(self.plantilla.get("color_acento","#e94560"), "color_acento")
        fc.addRow("Fondo:", self.btn_color_fondo)
        fc.addRow("Texto:", self.btn_color_texto)
        fc.addRow("Acento:", self.btn_color_acento)
        ll.addWidget(grp_col)

        grp_prev = QGroupBox("Vista previa — nivel")
        gp = QVBoxLayout(grp_prev)
        self.cmb_nivel_prev = create_combo(); self.cmb_nivel_prev.addItems(list(NIVELES.keys()))
        self.cmb_nivel_prev.currentTextChanged.connect(self._update_preview)
        gp.addWidget(self.cmb_nivel_prev)
        ll.addWidget(grp_prev)

        btn_save = create_success_button("💾 Guardar plantilla")
        apply_tooltip(btn_save, "Guardar configuración de la plantilla actual")
        btn_save.clicked.connect(self._guardar_plantilla)
        ll.addWidget(btn_save); ll.addStretch()
        lay.addWidget(left)

        # Panel derecho: vista previa
        right = QWidget(); rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Vista previa (escala de pantalla):"))
        self.preview = CardPreviewRenderer()
        self._update_preview()
        scroll = QScrollArea(); scroll.setWidget(self.preview); scroll.setWidgetResizable(False)
        rl.addWidget(scroll, 0, Qt.AlignHCenter)
        rl.addStretch()
        lay.addWidget(right)
        return w

    def _mk_color_btn(self, color: str, campo: str) -> QPushButton:
        btn = QPushButton(f"🎨 {campo.replace('color_', '').capitalize()}")
        spj_btn(btn, "secondary")
        btn.setStyleSheet(f"background:{color};color:{'white' if color.startswith('#') and len(color) > 1 and color[1:3] < '80' else 'black'};font-weight:bold;")
        btn.setToolTip(f"Seleccionar color para {campo.replace('_', ' ')}")
        btn.clicked.connect(lambda _, c=campo, b=btn: self._pick_color(c, b))
        return btn

    def _pick_color(self, campo: str, btn: QPushButton):
        col = QColorDialog.getColor(QColor(self.plantilla.get(campo, "#000")), self)
        if col.isValid():
            hex_col = col.name()
            self.plantilla[campo] = hex_col
            label = f"🎨 {campo.replace('color_', '').capitalize()}"
            btn.setText(label)
            btn.setStyleSheet(f"background:{hex_col};color:{'white' if hex_col.startswith('#') and len(hex_col) > 1 and hex_col[1:3] < '80' else 'black'};font-weight:bold;")
            self._update_preview()

    def _seleccionar_logo(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar logo", "", "Imágenes (*.png *.jpg *.jpeg *.svg)")
        if ruta:
            self.txt_logo_path.setText(ruta)
            self.plantilla["logo_path"] = ruta
            self._update_preview()

    def _seleccionar_fondo(self):
        """v13.30: Seleccionar imagen de fondo para la tarjeta."""
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar fondo de tarjeta", "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp)")
        if ruta:
            self.txt_bg_path.setText(ruta)
            self.plantilla["bg_image_path"] = ruta
            self._update_preview()

    def _on_plantilla_change(self):
        self.plantilla["nombre_empresa"] = self.txt_nombre_emp.text()
        self.plantilla["eslogan"]        = self.txt_eslogan.text()
        if hasattr(self, 'txt_bg_path'):
            self.plantilla["bg_image_path"] = self.txt_bg_path.text()
        self._update_preview()

    def _update_preview(self):
        self.preview.actualizar(self.plantilla, self.cmb_nivel_prev.currentText())

    def _guardar_plantilla(self):
        self._on_plantilla_change()
        self._save_plantilla()
        QMessageBox.information(self, "✅", "Plantilla guardada correctamente.")

    # ── Tab 2: Configurar QR ────────────────────────────────────────────────

    def _build_tab_qr(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)

        info = QLabel(
            "Define qué información se codifica en el QR de cada tarjeta.\n"
            "El cajero escanea el QR para identificar al cliente en el POS.\n"
            "El cliente puede escanear el QR para ver el contenido.")
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        grp = QGroupBox("Campos del QR")
        form = QFormLayout(grp)
        chk_id = QCheckBox("Incluir ID de tarjeta (siempre activo)"); chk_id.setChecked(True); chk_id.setEnabled(False)
        self.qr_website   = create_input();   self.qr_website.setPlaceholderText("https://www.tunegocio.mx")
        self.qr_whatsapp  = create_input(); self.qr_whatsapp.setPlaceholderText("+52 999 123 4567")
        self.qr_facebook  = create_input();  self.qr_facebook.setPlaceholderText("facebook.com/tunegocio")
        self.qr_instagram = create_input();self.qr_instagram.setPlaceholderText("@tunegocio")
        self.qr_tiktok    = create_input();    self.qr_tiktok.setPlaceholderText("@tunegocio")
        self.cmb_sep      = create_combo(); self.cmb_sep.addItems(["|", ";", ",", " "])
        form.addRow("", chk_id)
        form.addRow("🌐 Página web:", self.qr_website)
        form.addRow("📱 WhatsApp:", self.qr_whatsapp)
        form.addRow("📘 Facebook:", self.qr_facebook)
        form.addRow("📸 Instagram:", self.qr_instagram)
        form.addRow("🎵 TikTok:", self.qr_tiktok)
        form.addRow("Separador:", self.cmb_sep)
        lay.addWidget(grp)

        grp_prev = QGroupBox("Vista previa del contenido QR")
        gpl = QVBoxLayout(grp_prev)
        self.lbl_qr_preview = QLabel()
        self.lbl_qr_preview.setObjectName("codeBlock")
        self.lbl_qr_preview.setWordWrap(True)
        gpl.addWidget(self.lbl_qr_preview)
        for field in [self.qr_website, self.qr_whatsapp, self.qr_facebook,
                      self.qr_instagram, self.qr_tiktok]:
            field.textChanged.connect(self._update_qr_preview)
        self.cmb_sep.currentTextChanged.connect(self._update_qr_preview)
        lay.addWidget(grp_prev)
        self._update_qr_preview()

        btn = create_primary_button("💾 Guardar configuración QR")
        apply_tooltip(btn, "Guardar configuración de campos QR")
        btn.clicked.connect(self._guardar_qr_config)
        lay.addWidget(btn, 0, Qt.AlignRight)
        lay.addStretch()
        return w

    def _update_qr_preview(self):
        sep = self.cmb_sep.currentText()
        parts = ["SPJ000001"]
        if self.qr_website.text():   parts.append(f"WEB:{self.qr_website.text()}")
        if self.qr_whatsapp.text():  parts.append(f"WA:{self.qr_whatsapp.text()}")
        if self.qr_facebook.text():  parts.append(f"FB:{self.qr_facebook.text()}")
        if self.qr_instagram.text(): parts.append(f"IG:{self.qr_instagram.text()}")
        if self.qr_tiktok.text():    parts.append(f"TT:{self.qr_tiktok.text()}")
        preview = sep.join(parts)
        self.lbl_qr_preview.setText(f"Ejemplo: {preview}")

    def _guardar_qr_config(self):
        self.plantilla.update({
            "qr_website": self.qr_website.text().strip(),
            "qr_whatsapp": self.qr_whatsapp.text().strip(),
            "qr_facebook": self.qr_facebook.text().strip(),
            "qr_instagram": self.qr_instagram.text().strip(),
            "qr_tiktok": self.qr_tiktok.text().strip(),
            "qr_separador": self.cmb_sep.currentText(),
        })
        self._save_plantilla()
        QMessageBox.information(self, "✅", "Configuración QR guardada.")

    # ── Tab 3: Generar Lote PDF ─────────────────────────────────────────────

    def _build_tab_lote(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)

        grp_filt = QGroupBox("Parámetros del lote")
        form = QFormLayout(grp_filt)
        self.spin_cantidad  = QSpinBox(); self.spin_cantidad.setRange(1, 10000); self.spin_cantidad.setValue(100)
        self.cmb_nivel_lote = create_combo(); self.cmb_nivel_lote.addItem("Todos"); self.cmb_nivel_lote.addItems(list(NIVELES.keys()))
        self.chk_sin_asignar = QCheckBox("Solo tarjetas sin cliente asignado")
        form.addRow("Cantidad:", self.spin_cantidad)
        form.addRow("Nivel:", self.cmb_nivel_lote)
        form.addRow("", self.chk_sin_asignar)
        lay.addWidget(grp_filt)

        self.progress_lote = QProgressBar(); self.progress_lote.setVisible(False)
        self.lbl_progreso   = QLabel(""); self.lbl_progreso.setVisible(False)
        lay.addWidget(self.progress_lote); lay.addWidget(self.lbl_progreso)

        btn_row = QHBoxLayout()
        self.btn_generar = create_danger_button("🖨️ Generar PDF para imprenta")
        apply_tooltip(self.btn_generar, "Generar lote de tarjetas en PDF para impresión")
        self.btn_generar.clicked.connect(self._generar_lote)
        btn_row.addStretch(); btn_row.addWidget(self.btn_generar)
        lay.addLayout(btn_row)

        info = QLabel(
            "💡 El PDF contiene 24 tarjetas por hoja (12×18 pulgadas) en grid 6×4 con marcas de corte.\n"
            "Envíalo a la imprenta en cartulina 350gr para obtener tarjetas de calidad.")
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info); lay.addStretch()
        return w

    def _generar_lote(self):
        cant   = self.spin_cantidad.value()
        nivel  = self.cmb_nivel_lote.currentText()
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar lote de tarjetas", f"tarjetas_{date.today()}.pdf", "PDF (*.pdf)")
        if not ruta: return

        # Build or fetch card list
        cards = self._build_card_list(cant, nivel)
        if not cards:
            QMessageBox.warning(self, "Sin tarjetas",
                "No hay tarjetas disponibles. Genera tarjetas en la pestaña Emitidas."); return

        self.btn_generar.setEnabled(False)
        self.progress_lote.setMaximum(len(cards)); self.progress_lote.setValue(0)
        self.progress_lote.setVisible(True); self.lbl_progreso.setVisible(True)

        self._pdf_worker = BatchPDFWorker(cards, self.plantilla, ruta)
        self._pdf_worker.progress.connect(
            lambda cur, tot: (self.progress_lote.setValue(cur),
                              self.lbl_progreso.setText(f"Generando... {cur}/{tot}")))
        self._pdf_worker.finished.connect(lambda path: self._on_pdf_done(path, len(cards), nivel))
        self._pdf_worker.error.connect(lambda e: (
            QMessageBox.critical(self, "Error", e),
            self.btn_generar.setEnabled(True),
            self.progress_lote.setVisible(False),
            self.lbl_progreso.setVisible(False)))
        self._pdf_worker.start()

    def _build_card_list(self, cant: int, nivel: str) -> list:
        """Builds card list from existing cards or generates new ones."""
        try:
            # v13.30: Use COALESCE to support both schema variants
            # (codigo_qr from m000 or codigo from legacy)
            query = """SELECT COALESCE(codigo_qr, codigo, numero) as card_code, nivel
                       FROM tarjetas_fidelidad
                       WHERE COALESCE(activa, CASE estado WHEN 'disponible' THEN 1
                             WHEN 'activa' THEN 1 ELSE 0 END, 1) = 1"""
            params = []
            if nivel != "Todos":
                query += " AND nivel=?"; params.append(nivel)
            if self.chk_sin_asignar.isChecked():
                query += " AND (id_cliente IS NULL OR id_cliente=0)"
            query += f" LIMIT {cant}"
            rows = self.conexion.execute(query, params).fetchall()
            if rows:
                return [{"codigo": r[0], "nivel": r[1]} for r in rows if r[0]]
        except Exception as e:
            logger.debug("_build_card_list query: %s", e)

        # Generate new codes if none exist
        n = min(cant, 500)
        nivel_real = nivel if nivel != "Todos" else "Bronce"
        cards = []
        try:
            for _ in range(n):
                codigo = f"SPJ{uuid.uuid4().hex[:8].upper()}"
                # Insert with both column names for compatibility
                try:
                    self.conexion.execute(
                        "INSERT OR IGNORE INTO tarjetas_fidelidad"
                        "(codigo_qr, codigo, nivel, estado, activa, es_pregenerada) "
                        "VALUES(?,?,?,?,1,1)",
                        (codigo, codigo, nivel_real, 'disponible'))
                except Exception:
                    # Fallback: try with just one column variant
                    try:
                        self.conexion.execute(
                            "INSERT OR IGNORE INTO tarjetas_fidelidad"
                            "(codigo_qr, nivel, estado, es_pregenerada) "
                            "VALUES(?,?,?,1)",
                            (codigo, nivel_real, 'disponible'))
                    except Exception:
                        self.conexion.execute(
                            "INSERT OR IGNORE INTO tarjetas_fidelidad"
                            "(codigo, nivel, activa, es_pregenerada) "
                            "VALUES(?,?,1,1)",
                            (codigo, nivel_real))
                cards.append({"codigo": codigo, "nivel": nivel_real})
            try:
                self.conexion.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("generate cards: %s", e)
        return cards

    def _on_pdf_done(self, path: str, count: int, nivel: str):
        self.btn_generar.setEnabled(True)
        self.progress_lote.setVisible(False); self.lbl_progreso.setVisible(False)
        # Save lote record
        try:
            self.conexion.execute(
                "INSERT INTO lotes_tarjetas_pdf(cantidad,nivel,ruta_pdf,plantilla,usuario) "
                "VALUES(?,?,?,?,?)",
                (count, nivel, path, json.dumps(self.plantilla), self.usuario))
            try: self.conexion.commit()
            except Exception: pass
        except Exception as e:
            logger.debug("_on_pdf_done: %s", e)

        resp = QMessageBox.question(
            self, "✅ PDF generado",
            f"{count} tarjetas generadas.\n\nRuta: {os.path.basename(path)}\n\n¿Abrir PDF?",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            import subprocess, sys
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        self._cargar_historial()

    # ── Tab 4: Emitidas ─────────────────────────────────────────────────────

    def _build_tab_emitidas(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)

        busq = QHBoxLayout()
        self.txt_buscar_tarj = QLineEdit(); self.txt_buscar_tarj.setPlaceholderText("Buscar código o cliente...")
        self.txt_buscar_tarj.textChanged.connect(self._filtrar_tarjetas)
        self.cmb_nivel_fil   = QComboBox(); self.cmb_nivel_fil.addItem("Todos"); self.cmb_nivel_fil.addItems(list(NIVELES.keys()))
        self.cmb_nivel_fil.currentTextChanged.connect(self._filtrar_tarjetas)
        busq.addWidget(self.txt_buscar_tarj, 2); busq.addWidget(self.cmb_nivel_fil)
        lay.addLayout(busq)

        self.tbl_tarj = QTableWidget(); self.tbl_tarj.setColumnCount(6)
        self.tbl_tarj.setHorizontalHeaderLabels(["Código","Nivel","Cliente","Puntos","Estado","Fecha"])
        hh = self.tbl_tarj.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_tarj.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_tarj.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_tarj.verticalHeader().setVisible(False)
        self.tbl_tarj.setAlternatingRowColors(True)
        lay.addWidget(self.tbl_tarj)

        acc = QHBoxLayout()
        for label, slot in [
            ("💰 Ajustar puntos", self._ajustar_puntos),
            ("⬆ Subir nivel", self._subir_nivel),
            ("🔒 Bloquear", self._bloquear),
            ("+ Asignar nueva", self._asignar_nueva)
        ]:
            btn = create_secondary_button(self, label)
            btn.clicked.connect(slot)
            acc.addWidget(btn)
        lay.addLayout(acc)
        return w

    def _cargar_tarjetas(self):
        try:
            rows = self.conexion.execute("""
                SELECT COALESCE(t.codigo_qr, t.codigo, t.numero) as card_code,
                       t.nivel,
                       COALESCE(c.nombre,'Sin asignar'),
                       COALESCE(t.puntos_actuales, t.puntos, 0),
                       CASE
                         WHEN t.activa=1 OR t.estado IN ('disponible','activa') THEN 'Activa'
                         WHEN t.activa=0 OR t.estado='bloqueada' THEN 'Bloqueada'
                         ELSE COALESCE(t.estado, 'Activa')
                       END,
                       COALESCE(t.fecha_emision, t.fecha_creacion, '')
                FROM tarjetas_fidelidad t
                LEFT JOIN clientes c ON c.id=t.id_cliente
                ORDER BY COALESCE(t.puntos_actuales, t.puntos, 0) DESC LIMIT 300
            """).fetchall()
        except Exception as e:
            logger.debug("_cargar_tarjetas: %s", e)
            rows = []
        LEVEL_COLORS = {"Bronce":"#CD7F32","Plata":"#A8A8A8","Oro":"#FFD700","Platino":"#E5E4E2","Black":"#9CA3AF"}
        self.tbl_tarj.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r):
                it = QTableWidgetItem(str(v) if v is not None else "")
                if ci == 1: it.setForeground(QColor(LEVEL_COLORS.get(str(v), "#E2E8F0")))
                if ci == 3: it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_tarj.setItem(ri, ci, it)

    def _filtrar_tarjetas(self):
        txt = self.txt_buscar_tarj.text().lower()
        nivel = self.cmb_nivel_fil.currentText()
        for i in range(self.tbl_tarj.rowCount()):
            cod = (self.tbl_tarj.item(i,0) or QTableWidgetItem()).text().lower()
            cli = (self.tbl_tarj.item(i,2) or QTableWidgetItem()).text().lower()
            niv = (self.tbl_tarj.item(i,1) or QTableWidgetItem()).text()
            vis = (not txt or txt in cod or txt in cli) and (nivel == "Todos" or niv == nivel)
            self.tbl_tarj.setRowHidden(i, not vis)

    def _selected_codigo(self) -> str | None:
        row = self.tbl_tarj.currentRow()
        if row < 0: QMessageBox.warning(self, "Aviso", "Selecciona una tarjeta."); return None
        return (self.tbl_tarj.item(row, 0) or QTableWidgetItem()).text()

    def _ajustar_puntos(self):
        cod = self._selected_codigo()
        if not cod: return
        from PyQt5.QtWidgets import QInputDialog
        pts, ok = QInputDialog.getInt(self, "Ajustar puntos", "Nuevos puntos totales:", 0, 0, 999999)
        if ok:
            try:
                self.conexion.execute("UPDATE tarjetas_fidelidad SET puntos=? WHERE codigo=?", (pts, cod))
                try: self.conexion.commit()
                except Exception: pass
                self._cargar_tarjetas()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _subir_nivel(self):
        cod = self._selected_codigo()
        if not cod: return
        row = self.tbl_tarj.currentRow()
        niv_act = (self.tbl_tarj.item(row, 1) or QTableWidgetItem()).text()
        niveles = list(NIVELES.keys()); idx = niveles.index(niv_act) if niv_act in niveles else 0
        if idx >= len(niveles) - 1:
            QMessageBox.information(self, "Máximo", "Ya está en el nivel máximo."); return
        nuevo = niveles[idx + 1]
        try:
            self.conexion.execute("UPDATE tarjetas_fidelidad SET nivel=? WHERE codigo=?", (nuevo, cod))
            try: self.conexion.commit()
            except Exception: pass
            self._cargar_tarjetas()
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _bloquear(self):
        cod = self._selected_codigo()
        if not cod: return
        if QMessageBox.question(self, "Bloquear", "¿Bloquear esta tarjeta?") != QMessageBox.Yes: return
        try:
            self.conexion.execute("UPDATE tarjetas_fidelidad SET activa=0 WHERE codigo=?", (cod,))
            try: self.conexion.commit()
            except Exception: pass
            self._cargar_tarjetas()
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _asignar_nueva(self):
        from PyQt5.QtWidgets import QDialog, QFormLayout, QComboBox, QDialogButtonBox
        dlg = QDialog(self); dlg.setWindowTitle("Asignar tarjeta"); dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        cmb_cli   = QComboBox()
        cmb_nivel = QComboBox(); cmb_nivel.addItems(list(NIVELES.keys()))
        try:
            rows = self.conexion.execute(
                "SELECT id,nombre FROM clientes WHERE activo=1 ORDER BY nombre LIMIT 300"
            ).fetchall()
            for r in rows: cmb_cli.addItem(r[1], r[0])
        except Exception: cmb_cli.addItem("Sin clientes", None)
        form.addRow("Cliente:", cmb_cli); form.addRow("Nivel:", cmb_nivel)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        cid = cmb_cli.currentData()
        if not cid: return
        codigo = f"SPJ{uuid.uuid4().hex[:8].upper()}"
        try:
            self.conexion.execute(
                "INSERT OR IGNORE INTO tarjetas_fidelidad(id_cliente,codigo,nivel,activa) "
                "VALUES(?,?,?,1)", (cid, codigo, cmb_nivel.currentText()))
            try: self.conexion.commit()
            except Exception: pass
            self._cargar_tarjetas()
            QMessageBox.information(self, "✅", f"Tarjeta {codigo} asignada.")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    # ── Tab 5: Historial lotes ──────────────────────────────────────────────

    def _build_tab_historial(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        self.tbl_hist_lotes = QTableWidget(); self.tbl_hist_lotes.setColumnCount(5)
        self.tbl_hist_lotes.setHorizontalHeaderLabels(
            ["Fecha","Cantidad","Nivel","Ruta PDF","Acciones"])
        hh = self.tbl_hist_lotes.horizontalHeader()
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.tbl_hist_lotes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_hist_lotes.verticalHeader().setVisible(False)
        self.tbl_hist_lotes.setAlternatingRowColors(True)
        lay.addWidget(self.tbl_hist_lotes)
        return w

    def _cargar_historial(self):
        try:
            rows = self.conexion.execute(
                "SELECT created_at,cantidad,nivel,ruta_pdf,id FROM lotes_tarjetas_pdf "
                "ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        except Exception: rows = []
        self.tbl_hist_lotes.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r[:4]):
                it = QTableWidgetItem(str(v) if v else "")
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.tbl_hist_lotes.setItem(ri, ci, it)
            ruta = r[3] or ""
            btn_w = QWidget(); bl = QHBoxLayout(btn_w); bl.setContentsMargins(2,2,2,2)
            btn_abr = create_secondary_button(self, "📄 Abrir PDF")
            apply_tooltip(btn_abr, "Abrir archivo PDF generado")
            btn_abr.setObjectName("smallBtn")
            btn_abr.setEnabled(bool(ruta and os.path.exists(ruta)))
            btn_abr.clicked.connect(lambda _, p=ruta: self._abrir_pdf(p))
            bl.addWidget(btn_abr)
            self.tbl_hist_lotes.setCellWidget(ri, 4, btn_w)

    def _abrir_pdf(self, path: str):
        import subprocess, sys
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": subprocess.run(["open", path])
            else: subprocess.run(["xdg-open", path])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_tab_change(self, idx: int):
        if idx == 3: self._cargar_tarjetas()
        elif idx == 4: self._cargar_historial()
