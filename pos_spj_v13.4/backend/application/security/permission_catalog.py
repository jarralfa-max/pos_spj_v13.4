"""Catálogo canónico de permisos — `MODULO -> [accion, ...]`.

Es el vocabulario completo de permisos otorgables del ERP: lo que la matriz de
Configuración → Seguridad → Permisos debe ofrecer, y contra lo que se contrasta
lo que ya está guardado en `rol_permisos(rol_id, modulo, accion, permitido)`.

Vive en `backend/application/` y no en `backend/security/` a propósito: agrega
el vocabulario que declaran los contextos acotados (`backend/application/<ctx>/
permissions.py`), así que depende de ellos y tiene que estar por encima. El
formato del código en sí (`permission_code`, `normalize_permission`) no depende
de nada y por eso vive abajo, en `backend/security/permissions/codes.py`.

CÓMO SE CONSTRUYE — dos fuentes, y ninguna es una lista copiada a mano:

1. DERIVADO (`_CONTEXT_PERMISSION_MODULES`). Cada contexto acotado ya declara
   su vocabulario granular en su propio `permissions.py` y exporta un
   `ALL_*_PERMISSIONS`. El catálogo los lee y los descompone en módulo+acción.
   El contexto es el dueño: añadir un permiso allí lo publica aquí solo, sin
   tocar este archivo. Esto es lo que evita la duplicación que §26 prohíbe.

2. DECLARADO (`_DECLARED_MODULE_ACTIONS`). Módulos que hoy no tienen contexto
   acotado que los declare. Cada entrada lleva anotada la evidencia que la
   sostiene — el sembrado de `migrations/m000_base_schema.py`, un docstring
   superviviente, o el test de arquitectura que fija el valor. No hay ninguna
   entrada inventada: si no pude sostenerla con evidencia viva, no está.

DEUDA CONOCIDA, declarada y no disimulada:

- Cuatro contextos (`losses`, `pricing`, `suppliers`, `transfers`) todavía usan
  códigos PLANOS estilo `TRANSFERS_APPROVE`, sin el formato `MODULO.accion`.
  No se pueden derivar y NO se traducen aquí: inventarles un módulo sería
  fabricar vocabulario. Quedan fuera del catálogo y listados en
  `FLAT_CODE_CONTEXTS`. Mientras tanto sus acciones no son otorgables desde la
  matriz de permisos — que es exactamente el estado real, y por eso
  `TransferSessionPermissionChecker` traduce a mano el puñado de códigos que sí
  tienen contrapartida y deniega el resto (fail-closed).
- `FINANZAS` y `CLIENTES_CRM` son claves que el menú lateral canónico exige
  (`frontend/desktop/modules/{finance,customers_crm}/shell_registration.py`)
  pero que el sembrado de roles NO otorga: ahí siembra `FINANZAS_UNIFICADAS` y
  `CLIENTES`. Es una divergencia real y preexistente entre el menú y los roles
  sembrados — se declara para que la entrada del menú sea otorgable, pero
  ningún rol de sistema la trae de fábrica.
"""
from __future__ import annotations

from importlib import import_module

from backend.security.permissions.codes import split_permission

#: Contextos acotados que ya declaran vocabulario punteado `MODULO.accion`.
#: El catálogo los importa y deriva sus entradas. Que un contexto no esté aquí
#: significa que aún no tiene `permissions.py` con códigos punteados.
_CONTEXT_PERMISSION_MODULES = (
    "backend.application.analytics.permissions",
    "backend.application.assets.permissions",
    "backend.application.cash_register.permissions",
    "backend.application.configuracion.permissions",
    "backend.application.crm.permissions",
    "backend.application.customers.permissions",
    "backend.application.inventory.permissions",
    "backend.application.loyalty.permissions",
    "backend.application.loyalty_cards.permissions",
    "backend.application.meat_processing.permissions",
    "backend.application.orders_delivery.permissions",
    "backend.application.procurement.permissions",
    "backend.application.products.permissions",
    "backend.application.sales.permissions",
)

#: Contextos cuyos códigos siguen siendo planos (`LOSSES_VIEW`) y por eso no
#: entran al catálogo. No es una allowlist para tapar un fallo (§16): es el
#: registro explícito de una migración pendiente, y el test de arquitectura lo
#: usa para comprobar que la lista no crece.
FLAT_CODE_CONTEXTS = (
    "backend.application.losses.permissions",
    "backend.application.pricing.permissions",
    "backend.application.suppliers.permissions",
    "backend.application.transfers.permissions",
)

#: Las 5 acciones gruesas que `m000_base_schema._seed_system_roles()` otorga a
#: TODOS los módulos que siembra. Cualquier módulo del sembrado las tiene.
_SEEDED_COARSE_ACTIONS = ("ver", "crear", "editar", "eliminar", "exportar")

#: Módulos que siembra `_seed_system_roles()` en `rol_permisos`. Están en el
#: catálogo porque hay filas reales en la base con ese módulo: si faltaran, la
#: matriz de permisos mostraría filas huérfanas imposibles de reotorgar.
_SEEDED_MODULES = (
    "DASHBOARD", "POS", "INVENTARIO", "PRODUCTOS", "CLIENTES", "COMPRAS",
    "CAJA", "REPORTES_BI", "FINANZAS_UNIFICADAS", "TESORERIA", "RRHH",
    "CONFIGURACION", "USUARIOS", "DELIVERY", "COTIZACIONES", "MERMA",
    "PROVEEDORES", "PRODUCCION", "TRANSFERENCIAS",
)

#: Entradas declaradas a mano, cada una con su evidencia. El ORDEN importa:
#: `tests/architecture/test_settings_permission_catalog.py` compara
#: `CANONICAL_MODULE_PERMISSIONS["CONFIG_SEGURIDAD"] == ["ver", "editar"]` por
#: igualdad de lista, así que estas acciones se emiten en el orden declarado y
#: no alfabéticamente.
_DECLARED_MODULE_ACTIONS: dict[str, tuple[str, ...]] = {
    # Stubs de las tres entradas de Configuración del menú anterior. El test
    # SET-1 fija estos valores exactos para que no se renombren en silencio.
    "CONFIG_HARDWARE": ("ver",),
    "CONFIG_MODULOS": ("ver",),
    "CONFIG_SEGURIDAD": ("ver", "editar"),

    # Ciclo de vida de valores de Configuración (borrador -> aprobar ->
    # activar -> rollback). Ningún contexto acotado lo declara todavía porque
    # el módulo de Configuration Governance no existe en la arquitectura
    # nueva; el vocabulario lo fija SET-1 en
    # tests/architecture/test_settings_permission_catalog.py.
    "CONFIGURACION": ("valor.crear", "valor.aprobar", "valor.activar", "valor.rollback"),

    # Dispositivos y Salida de Documentos: `configuracion/permissions.py` sólo
    # declara lo que la pantalla de Configuración necesita, no el vocabulario
    # completo de estos dos ámbitos, y ninguno tiene contexto acotado propio.
    # Estas acciones las fija SET-1 en
    # tests/architecture/test_settings_permission_catalog.py.
    "DISPOSITIVOS": ("probar", "diagnostico.ver"),
    "DOCUMENTOS": ("trabajo.reintentar", "reimprimir_sensible", "etiqueta.imprimir"),

    # Códigos planos previos a BI-2 que siguen otorgados en instalaciones
    # existentes. Se conservan por compatibilidad hacia atrás, tal como exige
    # tests/architecture/test_analytics_permissions_are_granular.py.
    #
    # La lista NO es la del test, que sólo nombra cinco: es la de
    # `SECTION_PERMISSION`
    # (backend/application/analytics/services/bi_dashboard_service.py), que es
    # código VIVO y decide qué secciones del tablero ve cada quien. Una sección
    # cuyo código no esté aquí no es otorgable desde la matriz de permisos y
    # queda invisible para todo el mundo salvo el administrador.
    "INTELIGENCIA_BI": (
        "ver", "ver_ventas", "ver_inventario", "ver_compras", "ver_caja",
        "ver_clientes", "ver_proveedores", "ver_finanzas", "ver_merma",
        "exportar", "configurar",
    ),

    # Entrada gruesa de Transferencias. El valor exacto está documentado en el
    # docstring de backend/application/transfers/session_authorization.py, que
    # traduce los códigos planos del contexto contra estas cuatro acciones.
    "TRANSFERENCIAS": ("ver", "crear", "recibir", "cancelar"),

    # Catálogo legado de Clientes (4 acciones). Documentado en el docstring de
    # backend/application/customers/permissions.py. Se conserva otorgable
    # porque hay roles que ya lo tienen; el código nuevo usa CLIENTES.*
    # granular.
    "CLIENTES": ("ver", "crear", "editar", "credito"),

    # Claves que el menú lateral canónico exige y el sembrado NO otorga (ver
    # la nota de deuda en el docstring del módulo).
    "FINANZAS": _SEEDED_COARSE_ACTIONS,
    "CLIENTES_CRM": _SEEDED_COARSE_ACTIONS,
}


def _derived_module_actions() -> dict[str, list[str]]:
    """Acciones que publican los contextos acotados, por módulo.

    Un contexto que no importe se propaga como error en vez de omitirse: un
    hueco silencioso en el vocabulario de permisos haría que la matriz dejara
    de ofrecer acciones que los casos de uso sí exigen, y nadie lo notaría
    hasta que a alguien le faltara un permiso que no puede otorgarse.
    """
    derived: dict[str, list[str]] = {}
    for dotted in _CONTEXT_PERMISSION_MODULES:
        module = import_module(dotted)
        codes: set[str] = set()
        for name in dir(module):
            if name.startswith("ALL_") and name.endswith("_PERMISSIONS"):
                codes.update(getattr(module, name))
        for code in codes:
            module_key, action = split_permission(code)
            if not module_key:
                # Código plano en un contexto que se declaró punteado.
                continue
            bucket = derived.setdefault(module_key, [])
            if action not in bucket:
                bucket.append(action)
    return derived


def _build_catalog() -> dict[str, list[str]]:
    catalog: dict[str, list[str]] = {}
    derived = _derived_module_actions()

    def add(module_key: str, actions) -> None:
        bucket = catalog.setdefault(module_key, [])
        for action in actions:
            if action not in bucket:
                bucket.append(action)

    # 1. Declarado primero, para que su orden sobreviva a la igualdad de lista
    #    que comprueban los tests de SET-1.
    for module_key, actions in _DECLARED_MODULE_ACTIONS.items():
        add(module_key, actions)

    # 2. Acciones gruesas del sembrado, SÓLO para módulos sin contexto acotado
    #    que los declare.
    #
    #    Cuando un módulo sí tiene dueño, su vocabulario granular SUSTITUYE al
    #    stub grueso — no se le suma. Es lo que documenta la migración 179 para
    #    Inventario: al adoptar el catálogo granular, las acciones gruesas
    #    anteriores quedaron "inertes" en `rol_permisos` y NO se expandieron a
    #    las granulares, porque hacerlo habría sido escalamiento de privilegios.
    #    Añadir aquí `INVENTARIO.editar` volvería a hacer otorgable justo el
    #    permiso grueso que esa migración retiró. Tres tests de lockstep
    #    (INVENTARIO, PRODUCTOS, CAJA) exigen igualdad exacta entre catálogo y
    #    contexto, y son los que fijan esta regla.
    for module_key in _SEEDED_MODULES:
        if module_key in derived:
            continue
        add(module_key, _SEEDED_COARSE_ACTIONS)

    # 3. Vocabulario granular de los contextos acotados, en orden estable.
    for module_key, actions in derived.items():
        add(module_key, sorted(actions))

    return catalog


#: `MODULO -> [accion, ...]`. Construido una sola vez al importar.
CANONICAL_MODULE_PERMISSIONS: dict[str, list[str]] = _build_catalog()
