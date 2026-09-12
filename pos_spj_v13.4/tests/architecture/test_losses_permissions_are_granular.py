from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_losses_permission_catalog_does_not_define_general_merma_permissions():
    source = (ROOT / "backend/application/losses/permissions.py").read_text(encoding="utf-8")
    assert '"MERMA"' not in source
    assert '"MERMA.crear"' not in source
    assert '"MERMA.autorizar"' not in source


def test_losses_authorization_is_backend_owned_and_fail_closed():
    source = (ROOT / "backend/application/losses/authorization.py").read_text(encoding="utf-8")
    assert "LossConfigurationError" in source
    assert "APPROVE_OVER_LIMIT" in source
    assert "LossSegregationOfDutiesError" in source


def test_the_legacy_coarse_permissions_are_gone_with_their_module():
    """Esta prueba fijaba una DEUDA, no una garantía.

    Afirmaba que `modulos/merma.py` siguiera usando los permisos gruesos
    `MERMA.crear`/`MERMA.autorizar` "hasta el corte de UI". El corte ocurrió
    —por borrado— y el archivo ya no existe, así que la prueba llevaba fallando
    con `FileNotFoundError`, que es la peor forma de reportar un éxito.

    Se invierte: lo que hay que vigilar ahora es que ese módulo no vuelva, y
    que los permisos gruesos no reaparezcan en el código canónico.
    """
    assert not (ROOT / "modulos" / "merma.py").exists(), (
        "Volvió el módulo legacy de Mermas: revisa de nuevo sus permisos.")

    gruesos = ('"MERMA.crear"', '"MERMA.autorizar"')
    reincidentes = [
        str(path.relative_to(ROOT))
        for raiz in ("backend", "frontend")
        for path in (ROOT / raiz).rglob("*.py")
        if "__pycache__" not in path.parts
        and any(g in path.read_text(encoding="utf-8", errors="ignore") for g in gruesos)
    ]
    assert not reincidentes, f"Permisos gruesos de Mermas de vuelta en: {reincidentes}"
