"""Buscador de sucursales.

REGLA DE SEGURIDAD — este widget NO filtra nada.

El alcance se resuelve ANTES de consultar, en
`backend/application/security/branch_scope_query_service.py`, y el orden es
`usuario → sucursales permitidas → consulta → resultados`. Lo contrario
—traer todas las sucursales y ocultar aquí las no permitidas— sería una fuga de
información: bastaría conocer el nombre para descubrir por búsqueda una sucursal
a la que los permisos no dan acceso.

Por eso el `provider` que se inyecta aquí YA viene acotado al usuario. Si algún
día alguien le pasa un provider sin acotar, el fallo estará en la composición,
no en esta clase — que deliberadamente no tiene con qué defenderse.

`empty_reason_provider` explica POR QUÉ no hubo resultados ("no tienes
sucursales asignadas" ≠ "ninguna coincide" ≠ "están inactivas"). Sin él, la
falta de alcance se ve igual que un buscador roto.
"""

from __future__ import annotations

from typing import Callable

from frontend.desktop.components.search_selector import SearchProvider, SearchSelector


class BranchSearchBox(SearchSelector):
    def __init__(
        self, parent=None, *, provider: SearchProvider | None = None,
        empty_reason_provider: Callable[[str], str | None] | None = None,
    ) -> None:
        super().__init__(
            parent, provider=provider, placeholder="Buscar sucursal...",
            empty_reason_provider=empty_reason_provider)


#: El encargo lo nombró `BranchSelector`. Es un ALIAS del mismo objeto, no un
#: widget paralelo: la familia de este código se llama `<Entidad>SearchBox`
#: (`AssetSearchBox`, `CustomerSearchBox`, `DriverSearchBox`), y crear un
#: segundo widget con otro nombre para lo mismo sería justo la dispersión que
#: el contrato compartido existe para evitar.
BranchSelector = BranchSearchBox
