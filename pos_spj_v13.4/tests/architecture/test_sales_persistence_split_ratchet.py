"""§3 al nivel de DATOS: hubo DOS modelos de persistencia vivos para una venta.

ESTADO AL 2026-10-01 (re-auditoría POS), medido, no supuesto: la tabla legacy
`ventas` tiene **CERO escritores productivos**. Los 10 que había el 2026-09-08
(la API REST, `SalesService`, `SalesReversalService`, la proyección de
Delivery, tres repositorios y el adaptador POS) se borraron con `api/`,
`core/`, `repositories/`, `integrations/` e `infrastructure/`. Toda venta nace
en el agregado canónico `sales`/`sale_lines`/..., que escribe UN solo archivo
(`backend/infrastructure/db/repositories/sales/sale_repository.py`, vía
`SalesUnitOfWork`).

Quedan LECTORES de `ventas` (consultas sin importadores productivos, que ya
sólo ven datos históricos); esta prueba no los cuenta.

Historia, para no reabrir la investigación: el 2026-09-08 una venta cobrada en
el POS aterrizaba en `sales` mientras BI / forecast / historial de cliente /
planeación de compras leían `ventas`.

Por qué esto es un ratchet y no un `assert` de corte:

Unificar exige un corte de datos (migrar `ventas` -> `sales`, o dar al
repositorio canónico una implementación sobre las tablas legacy) y tocar los
49 lectores. Eso es una migración formal (§20) con parada obligatoria, no
algo que se resuelva de paso. Lo que sí se puede garantizar mientras tanto es
que la brecha **no crezca en silencio**: ningún archivo productivo nuevo
puede empezar a escribir la tabla legacy, y el lado canónico no puede
encoger. Cuando alguien migre un escritor, esta lista cambia y la prueba de
"no obsoleto" obliga a actualizar este archivo — que es lo que convierte el
corte en inevitable en vez de perpetuo.

Ojo con el docstring de `backend/infrastructure/db/schema/sales_schema.py`:
dice que `ventas` es "the only live write path". Era cierto en SALES-4 y dejó
de serlo en SALES-19..22, cuando `modulos/ventas.py` se borró y `sales_pos`
pasó a ser la única pantalla de POS viva.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT

# Directorios productivos: se excluyen tests/ y migrations/ a propósito
# (las migraciones DEBEN tocar el esquema; las pruebas siembran datos).
_PRODUCTION_DIRS = (
    "api", "backend", "core", "delivery", "frontend", "infrastructure",
    "integrations", "interfaz", "modulos", "repositories", "services", "sync",
)

_LEGACY_WRITE = re.compile(r"(?:INSERT\s+INTO|UPDATE)\s+ventas\b", re.IGNORECASE)
_CANONICAL_WRITE = re.compile(
    r"(?:INSERT\s+INTO|UPDATE)\s+(?:sales|sale_lines|sale_payments)\b", re.IGNORECASE)


def _production_files():
    for directory in _PRODUCTION_DIRS:
        root = APP_ROOT / directory
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def _writers(pattern) -> set[str]:
    found = set()
    for path in _production_files():
        source = path.read_text(encoding="utf-8", errors="ignore")
        # Se descartan las líneas de comentario y los docstrings que CITAN el
        # SQL retirado para explicar una corrección (el router de anular lo
        # hace); si no, la prueba marcaría como vivo lo que ya se quitó.
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("`"):
                continue
            if pattern.search(line) and '"""' not in line and "`" not in line:
                found.add(path.relative_to(APP_ROOT).as_posix())
                break
    return found


# Escritores productivos de la tabla LEGACY. Llegó a CERO el 2026-10-01 y no
# puede volver a crecer: ninguna venta nueva puede nacer fuera de `sales`.
_LEGACY_WRITERS: frozenset[str] = frozenset()

# El lado canónico escribe por UN solo sitio, que es justo lo que §3 pide.
# Esto no puede crecer sin una razón explícita: si aparece un segundo
# escritor, el agregado dejó de ser la única puerta.
_CANONICAL_WRITERS = frozenset({
    "backend/infrastructure/db/repositories/sales/sale_repository.py",
})


def test_legacy_sales_table_gains_no_new_writers() -> None:
    """Ningún archivo productivo nuevo puede empezar a escribir `ventas`."""
    current = _writers(_LEGACY_WRITE)
    new = current - _LEGACY_WRITERS
    assert not new, (
        "Escritores NUEVOS de la tabla legacy `ventas`. Toda venta nueva debe "
        "nacer en el agregado canónico (`sales`), no ampliar el modelo que se "
        "quiere retirar:\n  " + "\n  ".join(sorted(new))
    )


def test_legacy_writer_list_is_not_stale() -> None:
    """Si un escritor legacy migró, hay que registrarlo aquí.

    Sin esto la lista envejece y deja de comunicar, que es el falso gate que
    §40 describe: una allowlist que nadie actualiza.
    """
    current = _writers(_LEGACY_WRITE)
    gone = _LEGACY_WRITERS - current
    assert not gone, (
        "Estos archivos ya no escriben `ventas`: el corte avanzó y hay que "
        "reflejarlo en _LEGACY_WRITERS (y en el conteo del docstring):\n  "
        + "\n  ".join(sorted(gone))
    )


def test_canonical_aggregate_has_exactly_one_write_door() -> None:
    current = _writers(_CANONICAL_WRITE)
    assert current == set(_CANONICAL_WRITERS), (
        "El agregado canónico de Ventas debe escribirse por un único "
        f"repositorio (§3). Medido: {sorted(current)}"
    )


def test_the_gap_is_an_explicit_number_not_prose() -> None:
    """La brecha, comprobada, no narrada."""
    legacy = _writers(_LEGACY_WRITE)
    assert len(legacy) == 0, (
        f"Los escritores de `ventas` pasaron de 0 a {len(legacy)}. Actualiza "
        "este número y el docstring de este archivo:\n  " + "\n  ".join(sorted(legacy))
    )


def test_no_bridge_exists_between_the_two_models() -> None:
    """Si alguien construye el puente, esta prueba avisa de que el mapa de
    arriba dejó de ser cierto — no es un veto al puente, es su recordatorio.

    Se busca un archivo productivo que toque LAS DOS tablas por escritura:
    eso es exactamente lo que haría una proyección o un dual-write.
    """
    both = _writers(_LEGACY_WRITE) & _writers(_CANONICAL_WRITE)
    assert not both, (
        "Un archivo productivo escribe los DOS modelos de venta. Si es el "
        "puente/proyección del corte, documenta el nuevo estado en este "
        "archivo y en docs/:\n  " + "\n  ".join(sorted(both))
    )


def test_the_live_pos_persists_through_the_canonical_aggregate() -> None:
    """Fija la dirección del hallazgo: el POS que el usuario usa NO escribe
    la tabla legacy. Si esto cambia, el diagnóstico de este archivo cambia.

    El POS vivo lo monta el shell canónico (`ApplicationWindow`); el
    `interfaz/main_window.py` que esta prueba leía se borró con el shell
    legacy."""
    checkout = (APP_ROOT / "backend/application/sales/use_cases/checkout_use_cases.py"
                ).read_text(encoding="utf-8", errors="ignore")
    assert "SalesUnitOfWork" in checkout
    assert not _LEGACY_WRITE.search(checkout)
    assert not re.search(r"\bFROM\s+ventas\b", checkout, re.IGNORECASE)

    presenter = (APP_ROOT / "frontend/desktop/modules/sales_pos/sales_pos_presenter.py"
                 ).read_text(encoding="utf-8", errors="ignore")
    assert "checkout_sale" in presenter

    shell = (APP_ROOT / "frontend/desktop/shell/desktop_shell_window_composition.py"
             ).read_text(encoding="utf-8", errors="ignore")
    assert "frontend.desktop.modules.sales_pos.shell_registration" in shell
