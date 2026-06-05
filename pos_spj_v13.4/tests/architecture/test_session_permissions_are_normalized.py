from core.session_context import SessionContext


def test_session_permissions_are_case_insensitive_and_star_allows_all() -> None:
    session = SessionContext()
    session.set_user({"id": 1, "username": "caja", "rol": "cajero"})
    session.set_permisos({"pos.VER"})

    assert session.tiene_permiso("POS.ver")
    assert session.tiene_permiso("pos.ver")
    assert session.tiene_permiso("Pos.Ver")
    assert not session.tiene_permiso("CAJA.ver")

    session.set_permisos({"*"})
    assert session.tiene_permiso("CAJA.ver")
