"""Reference-layout evidence with production Qt widgets and labeled test data.

This is presentation evidence, not a real payment, scale sample or configured
campaign. The Configuracion integration test separately covers media resolution.
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.components.branding import BrandAssetProvider
from frontend.desktop.modules.sales_pos.customer_display_window import CustomerDisplayWindow
from frontend.desktop.themes.theme_manager import ThemeManager


def main():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if os.name == "nt":
        for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / font))
    ThemeManager.instance().apply(app, "light", density="comfortable")
    out = Path(__file__).resolve().parents[2] / "docs/refactor/evidence/customer_display_followup"
    out.mkdir(parents=True, exist_ok=True)
    media = out / "official_media_fixture.png"
    BrandAssetProvider.pixmap("logo_horizontal_dark", QSize(640, 240)).save(str(media))
    content = {
        "BRANDING": {"name": "JUANIS", "tagline": "Calidad que viene de familia"},
        "ITEMS": [dict(name=name, quantity=quantity, unit=unit, line_total=amount)
                  for name, quantity, unit, amount in (
                      ("Pechuga", "1.250", "kg", "118.75"),
                      ("Pierna y muslo", "2", "kg", "140"),
                      ("Alas", "1", "kg", "85"), ("Arroz", "2", "kg", "64"),
                      ("Aceite", "1", "pza", "52"))],
        "TOTAL": "459.75", "SCALE": "Peso actual de báscula\n0.850 kg · estable",
        "POINTS": "Puntos estimados\n+45",
    }
    window = CustomerDisplayWindow()
    window.resize(1280, 720)
    window.render_content("CART", content)
    window.render_idle_ad("IMAGE", "Recurso de prueba", "", str(media), during_sale=True)
    QTest.qWait(50)
    window.grab().save(str(out / "cart_with_ad.png"))
    window.render_content("THANK_YOU", {
        "BRANDING": content["BRANDING"], "TOTAL": "459.75",
        "MESSAGE": "¡Gracias por tu compra!\n¡Te esperamos pronto!",
        "POINTS": "+45 puntos acreditados",
    })
    QTest.qWait(50)
    window.grab().save(str(out / "completion_forest.png"))
    window.close()
    print(f"Saved presentation fixtures in {out}")


if __name__ == "__main__":
    main()
