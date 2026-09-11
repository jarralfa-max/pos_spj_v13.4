"""Mermas: una sola entrada en el menú, un solo anfitrión, y páginas sin base.

DOS DE ESTAS PRUEBAS APUNTABAN A ARCHIVOS BORRADOS
--------------------------------------------------
Leían `interfaz/main_window.py` y `interfaz/menu_lateral.py` con `read_text()`,
así que desde que esas carpetas desaparecieron fallaban con `FileNotFoundError`
— un fallo que no dice nada sobre Mermas y que se acaba ignorando como ruido.

Además comprobaban la FORMA de la API del shell anterior
(`self._conectar("MERMAS", ...)`, `self._crear_boton("Mermas", "MERMAS")`), que
el shell canónico no usa: aquí las entradas son `NavigationItemDefinition`. No
se podían repuntar, había que reescribirlas contra lo que existe.

Lo que se comprueba sigue siendo lo mismo, que es lo que importa: que Mermas
aparezca UNA vez en el menú y que nadie resucite un segundo anfitrión.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_LOSSES_MODULE = ROOT / "frontend/desktop/modules/losses"
_NAVIGATION = ROOT / "frontend/desktop/shell/sidebar/migrated_modules_navigation.py"

#: Emoji: los rangos que de hecho aparecían en el menú anterior (pictogramas,
#: transporte, símbolos misceláneos y banderas). El menú canónico usa `Icons.*`.
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def test_losses_view_uses_sidebar_and_stack_not_horizontal_tabs():
    source = (_LOSSES_MODULE / "losses_view.py").read_text(encoding="utf-8")
    assert "LossesSidebarWidget" in source
    assert "QStackedWidget" in source
    assert "QTabWidget" not in source


def test_the_shell_hosts_losses_through_the_canonical_factory_only():
    """Un segundo anfitrión significa dos pantallas de Mermas vivas a la vez,
    cada una con su propio estado — y la que vea el usuario depende de por
    dónde entró."""
    registro = (_LOSSES_MODULE / "shell_registration.py").read_text(encoding="utf-8")
    assert "from backend.infrastructure.desktop.losses_factory import create_losses_view" in registro

    # `ModuloMerma` era el anfitrión legacy. Que no reaparezca en ningún sitio.
    resucitado = [
        str(path.relative_to(ROOT))
        for raiz in (ROOT / "frontend", ROOT / "backend")
        for path in raiz.rglob("*.py")
        if "__pycache__" not in path.parts
        and "ModuloMerma" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not resucitado, f"El anfitrión legacy de Mermas volvió: {resucitado}"


def test_the_sidebar_has_exactly_one_losses_entry_without_emoji():
    """Dos entradas al mismo módulo confunden sin fallar: las dos abren algo."""
    source = _NAVIGATION.read_text(encoding="utf-8")

    entradas = re.findall(r'item_id="(nav\.losses[^"]*)"', source)
    assert entradas == ["nav.losses"], f"entradas de Mermas en el menú: {entradas}"

    etiquetas = re.findall(r'item_id="nav\.losses".*?label="([^"]+)"', source, re.DOTALL)
    assert etiquetas, "la entrada de Mermas no tiene etiqueta"
    assert not _EMOJI_RE.search(etiquetas[0]), (
        f"la etiqueta del menú lleva emoji: {etiquetas[0]!r}")


def test_losses_pages_do_not_access_database_or_repositories():
    """`.execute(` a secas marcaba TAMBIÉN `use_case.execute(...)`.

    Es decir, cualquier presentador que invoque un caso de uso — que es lo que
    un presentador debe hacer. Esta guardia llevaba roja por ese motivo falso,
    y una guardia que siempre está roja deja de leerse. Ahora se exige que el
    receptor de `.execute(` sea una conexión, una base o un cursor.
    """
    acceso_a_base = re.compile(
        r"\bsqlite3\b"
        r"|\b\w*(?:conn|cnx|db|cursor)\w*\s*(?:\(\s*\))?\s*\.\s*"
        r"(?:execute|executemany|executescript|commit|rollback|cursor)\s*\("
        r"|\brepositories\b",
        re.IGNORECASE,
    )
    offenders = []
    for path in _LOSSES_MODULE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for numero, linea in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if acceso_a_base.search(linea):
                offenders.append(f"{path.relative_to(ROOT)}:{numero}: {linea.strip()}")
    assert not offenders, "Las páginas de Mermas tocan la base:\n" + "\n".join(offenders)
