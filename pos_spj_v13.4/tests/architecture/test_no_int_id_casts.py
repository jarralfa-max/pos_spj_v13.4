"""REGLA CERO: prohibido convertir identidades de dominio con int(..._id).

UUIDv7 es la única identidad persistente. Cualquier cast int() sobre un
identificador funcional (producto, venta, sucursal, cliente, usuario, rol,
lote, compra, reserva…) rompe RBAC y los contratos UUID.
"""

from __future__ import annotations

import re
from pathlib import Path

from .architecture_guardrails import (
    APP_ROOT,
    PYTHON_SUFFIXES,
    assert_no_new_violations,
    collect_regex_violations,
    iter_files,
    outside_migrations,
)

INT_ID_CAST_RE = re.compile(r"\bint\(\s*(?:\w+\.)?\w*_(?:id|row_id)\s*\)")

# Deuda saldada: cero casts int(..._id) permitidos.
INT_ID_CASTS_ALLOWLIST: dict[str, int] = {}


def test_no_int_id_casts() -> None:
    violations = collect_regex_violations(
        pattern=INT_ID_CAST_RE,
        roots=(APP_ROOT,),
        path_filter=outside_migrations,
        code_only=True,
    )
    assert_no_new_violations("int(..._id) cast", violations, INT_ID_CASTS_ALLOWLIST)


#: Donde viven HOY RBAC y la sesion.
#:
#: Esta guardia vigilaba `repositories/config_repository.py`,
#: `core/session_context.py`, `security/` y `repositories/security_repository.py`.
#: Las cuatro se borraron y la prueba siguio en verde sin leer nada, porque
#: `iter_files` salta las raices inexistentes.
#:
#: Y ya era ciega antes: tres de las cuatro eran ARCHIVOS, y
#: `Path(archivo).rglob("*")` no devuelve nada. Ni cuando existian se
#: escanearon; solo `security/`, un directorio, se leia de verdad.
_CRITICAL_ROOTS_RELATIVE = (
    "backend/security",
    "backend/application/security",
    "backend/infrastructure/db/repositories/security",
    "backend/infrastructure/db/repositories/settings",
    "backend/bootstrap/legacy_session_adapter.py",
    "backend/api/mobile_session.py",
    "frontend/desktop/shell/modules/session_access.py",
)


def _critical_roots() -> tuple[Path, ...]:
    """Raices fijas mas un `session_authorization.py` por contexto.

    Los de contexto se DESCUBREN en vez de listarse: uno nuevo entra solo, y
    uno que desaparezca no deja un hueco escrito a mano.
    """
    por_contexto = sorted(
        (APP_ROOT / "backend" / "application").glob("*/session_authorization.py"))
    return tuple(APP_ROOT / r for r in _CRITICAL_ROOTS_RELATIVE) + tuple(por_contexto)


def test_no_int_id_casts_in_permissions_and_session() -> None:
    """RBAC y sesion no toleran NINGUN cast entero de identidad.

    La guardia general de arriba ya recorre toda la app con allowlist vacia;
    esta existe para que las rutas criticas sigan en tolerancia cero aunque un
    dia esa allowlist crezca.

    Antes de buscar casts se exige que cada raiz APORTE archivos. Sin eso, una
    ruta renombrada o borrada deja la prueba en verde leyendo cero lineas —
    que es exactamente como esta guardia paso meses sin proteger nada.
    """
    roots = _critical_roots()
    assert any(r.name == "session_authorization.py" for r in roots), (
        "No se encontro ningun `backend/application/*/session_authorization.py`: "
        "o se movieron o el patron de busqueda quedo obsoleto.")

    vacias = [r.relative_to(APP_ROOT).as_posix() for r in roots
              if not any(True for _ in iter_files(suffixes=PYTHON_SUFFIXES, roots=(r,)))]
    assert not vacias, (
        "Raices criticas que no aportan ningun archivo; la prueba pasaria sin "
        "leerlas:\n  " + "\n  ".join(vacias))

    violations = collect_regex_violations(pattern=INT_ID_CAST_RE, roots=roots, code_only=True)
    assert not violations, (
        "Casts int(..._id) en RBAC/sesion:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )
