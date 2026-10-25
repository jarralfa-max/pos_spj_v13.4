"""La política que recibe un caso de uso construido SIN política.

Auditoría global de permisos 968e0bc (PER-02). Unos 130 constructores de
Inventario, Procesamiento cárnico y Productos hacían

    self._auth = authorization or XAuthorizationPolicy.permissive_for_tests()

así que cualquier llamador que olvidara cablear la política —una integración,
un manejador de eventos, un refactor— operaba con TODO concedido, aunque el rol
o el usuario tuvieran el permiso revocado. Medido al cerrarlo: la entrada de
stock de cada compra, la salida por venta, las devoluciones y las reservas de
Pedidos llegaban así a Inventario.

Ahora ese default es `unwired(XAuthorizationPolicy)`: una política SIN
verificador, que falla cerrada en el primer `require()`. Los llamadores de
sistema usan una concesión nominada (`backend/application/inventory/
integration_grants.py`); la interfaz, el verificador de sesión.

En pruebas, `tests/conftest.py` sustituye `_resolver` por la política
permisiva EXPLÍCITA de cada contexto, para que las pruebas funcionales que
construyen casos de uso sueltos sigan probando su lógica. Las pruebas de
seguridad lo desactivan con la marca `unwired_fails_closed`.
"""
from __future__ import annotations


def _fail_closed(policy_cls):
    return policy_cls()


#: Punto único de resolución. Sólo las pruebas lo sustituyen.
_resolver = _fail_closed


def unwired(policy_cls):
    """Política para un caso de uso al que no le cablearon ninguna."""
    return _resolver(policy_cls)


__all__ = ["unwired"]
