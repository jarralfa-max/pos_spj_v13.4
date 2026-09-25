"""§1/§26 — el código de Procesamiento no conoce especies ni productos: ningún
nombre, cadena o identificador del programa menciona una especie o un corte.
Lo que distingue un proceso de otro es su FAMILIA (despiece, formulación,
empaque, acondicionado) y los datos de Productos.

"canal" no está en la lista: es el término genérico de sacrificio (canal de
cualquier especie), no una especie.
"""
import re

from tests.architecture._meat_processing_code import (
    code_strings,
    identifiers,
    production_files,
    rel,
)

ESPECIES = re.compile(
    r"\b(pollos?|gallinas?|aves?|av[ií]cola|poultry|chickens?|res(es)?|vacunos?|bovin[oa]s?|"
    r"beef|cattle|cerdos?|porcin[oa]s?|pork|pigs?|hogs?|pescados?|fish|mariscos?|seafood|"
    r"ovin[oa]s?|borregos?|cordero|lamb|caprin[oa]s?|chivos?|pechugas?|piernas?|muslos?|"
    r"alas|chuletas?|lomos?|filetes?|arrachera|costillas?)\b", re.I)


def _menciones(texto: str) -> list[str]:
    return ESPECIES.findall(texto.replace("_", " "))


def test_no_species_or_cut_in_processing_code():
    fugas = []
    for p in production_files():
        for linea, s in code_strings(p) + identifiers(p):
            if _menciones(s):
                fugas.append((rel(p), linea, s[:60]))
    assert fugas == []


def test_behaviour_is_chosen_by_process_family():
    from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
        PROCESS_FAMILIES,
        ProcessFamily,
    )
    from backend.domain.meat_processing.services.processing_execution_strategy import STRATEGIES

    assert set(STRATEGIES) == set(ProcessFamily)
    assert set(PROCESS_FAMILIES.values()) <= set(ProcessFamily)
