"""§9: dinero en `float()` — cero en el dominio, ratchet en el legacy.

`test_no_monetary_real_schema.py` cubre el ESQUEMA. Este cubre el CÓDIGO, que es
la otra mitad que §39 pide y que no existía.

Por qué dos garantías distintas en vez de una:

* `backend/domain/` está **hoy en cero** y se fija en cero duro. Es la capa que
  §4 obliga a mantener pura, y una regla que ya se cumple puede exigirse sin
  tolerancias. Es la línea que de verdad importa proteger.
* El resto del árbol arrastra **308** conversiones, 201 sólo en `core/`
  (`sales_service.py` 34, `finance_service.py` 20). Un assert a cero ahí sería
  un test rojo permanente, que es exactamente lo que §40 llama un falso gate:
  nadie lo lee y deja de comunicar. Se fija un ratchet por área que **no puede
  crecer**, de modo que la deuda existente queda medida y la nueva se bloquea.

Los números de `_LEGACY_BASELINE` son deuda **tolerada, no aprobada**. Bajan
conforme cada contexto migra a Decimal; nunca deben subir. Si un cambio los
reduce, hay que ratchetearlos hacia abajo en este archivo — ese es el mecanismo
que obliga a registrar el progreso.

Nota sobre el detector: busca `float(<identificador monetario>)`, no cualquier
`float(`. Convertir una cantidad para un gráfico o un porcentaje no es el
defecto; convertir un importe para operar con él sí lo es.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT

_MONETARY_TOKENS = (
    "price", "precio", "amount", "monto", "total", "subtotal", "cost", "costo",
    "importe", "saldo", "balance", "credit", "credito", "debit", "debito",
    "payment", "pago", "descuento", "discount", "impuesto", "tax", "iva",
    "comision", "commission", "unit_price", "valor",
)

_FLOAT_CALL_RE = re.compile(r"\bfloat\(\s*([A-Za-z_][\w\.\[\]\"']*)", re.IGNORECASE)

_SKIP_PARTS = {".venv", "venv", "site-packages", "node_modules", "__pycache__", ".git", "tests"}

# Deuda tolerada por área, medida en 3a5698b0. NO puede crecer.
_LEGACY_BASELINE = {
    "core": 201,
    "backend": 37,
    "repositories": 31,
    "modulos": 9,
    "application": 8,
    "integrations": 5,
    "scripts": 4,
    "utils": 3,
    "services": 2,
    "ui": 2,
    "frontend": 2,
    "interfaz": 1,
    "webapp": 1,
    "migrations": 1,
    "api": 1,
}


def _monetary_float_hits(root):
    hits = []
    for path in sorted(root.rglob("*.py")):
        if _SKIP_PARTS & set(path.parts):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for match in _FLOAT_CALL_RE.finditer(source):
            expression = match.group(1).lower()
            if not any(token in expression for token in _MONETARY_TOKENS):
                continue
            line = source.count("\n", 0, match.start()) + 1
            hits.append(f"{path.relative_to(APP_ROOT).as_posix()}:{line}: {match.group(0)}…)")
    return hits


def test_domain_layer_has_no_monetary_float() -> None:
    """`backend/domain/` es puro (§4) y hoy está limpio: cero duro, sin tolerancia."""
    offenders = _monetary_float_hits(APP_ROOT / "backend" / "domain")
    assert not offenders, (
        "float() sobre dinero en la capa de dominio — debe usar Decimal:\n"
        + "\n".join(offenders)
    )


def test_monetary_float_debt_does_not_increase() -> None:
    """Ratchet: la deuda legacy queda medida y no puede crecer."""
    counts: dict[str, int] = {}
    for hit in _monetary_float_hits(APP_ROOT):
        area = hit.split("/", 1)[0]
        counts[area] = counts.get(area, 0) + 1

    grown = [
        f"  {area}: {count} (permitido {_LEGACY_BASELINE.get(area, 0)})"
        for area, count in sorted(counts.items())
        if count > _LEGACY_BASELINE.get(area, 0)
    ]
    assert not grown, (
        "Deuda de float() sobre dinero AUMENTÓ. Usa Decimal en el código nuevo:\n"
        + "\n".join(grown)
    )


def test_baseline_has_no_stale_entries() -> None:
    """Si una migración a Decimal baja el conteo, hay que registrarlo aquí.

    Sin esta prueba el ratchet sólo impediría crecer, y el progreso quedaría sin
    documentar — que es como las allowlists de este repositorio acabaron
    tolerando deuda que ya no existía (ver 05_IDENTITY_GUARDRAILS.md).
    """
    counts: dict[str, int] = {}
    for hit in _monetary_float_hits(APP_ROOT):
        area = hit.split("/", 1)[0]
        counts[area] = counts.get(area, 0) + 1

    stale = [
        f"  {area}: real {counts.get(area, 0)} < base {allowed} — baja la base a {counts.get(area, 0)}"
        for area, allowed in sorted(_LEGACY_BASELINE.items())
        if counts.get(area, 0) < allowed
    ]
    assert not stale, "Baseline desactualizado (el progreso debe registrarse):\n" + "\n".join(stale)


def test_detector_distinguishes_money_from_other_floats() -> None:
    """El detector no puede degenerar en un no-op ni en ruido."""
    def _matches(line: str) -> bool:
        match = _FLOAT_CALL_RE.search(line)
        return bool(match) and any(t in match.group(1).lower() for t in _MONETARY_TOKENS)

    assert _matches("total = float(row['precio_unitario'])")
    assert _matches("x = float(venta.total)")
    assert _matches("float(monto)")
    # magnitudes no monetarias: no son este defecto
    assert not _matches("ratio = float(porcentaje_avance)")
    assert not _matches("lat = float(row['latitude'])")
    assert not _matches("n = float(contador)")
