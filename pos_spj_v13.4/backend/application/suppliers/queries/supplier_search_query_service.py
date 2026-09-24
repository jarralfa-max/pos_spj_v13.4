"""Búsqueda canónica de proveedores (§11) — UN solo contrato, presets por módulo.

Mismo criterio que `product_selection_query_service`: no debe existir una
versión por módulo. Cada módulo sólo AÑADE restricciones sobre este contrato.

QUÉ HABÍA ANTES, MEDIDO
------------------------
Dos buscadores contra DOS TABLAS DISTINTAS, con resultados disjuntos:

    Módulo Proveedores -> `supplier_master`  (el maestro canónico)
    Compras            -> `proveedores`      (la tabla heredada)

y NADA en el código de producción escribe en `proveedores` — sólo los tests.
Es decir: un proveedor dado de alta y aprobado hoy en el módulo de Proveedores
**no se podía elegir al crear una compra**, y los proveedores heredados que
Compras sí veía no aparecían en el módulo. No era un descuido: la migración 119
dejó escrito que esos lectores migrarían "en SUP-6"; para Compras nunca ocurrió.

La migración 263 copia los proveedores heredados al maestro CONSERVANDO su id,
para que las compras ya registradas sigan resolviendo su proveedor.

NORMALIZACIÓN — aquí sí se pliegan acentos, al revés que en Productos
---------------------------------------------------------------------
`supplier_repository.normalize_name` guarda `normalized_name` plegando acentos y
quitando TODO lo que no sea letra o dígito: "Carnes del Norte S.A." se almacena
como `carnesdelnortesa`. La búsqueda anterior comparaba contra el texto tal cual
(`normalized_name LIKE '%carnes del%'`), así que esa rama **no acertaba nunca**
en cuanto el término tenía un espacio o un punto; sólo funcionaba por
`legal_name`. Aquí el texto de búsqueda se normaliza EXACTAMENTE igual que lo
almacenado, que es lo único que permite compararlos.

Ojo con la diferencia respecto a Productos: allí NO se pliegan acentos, porque
el maestro de productos tampoco los pliega al persistir. La regla no es "plegar"
ni "no plegar", es **normalizar igual que escribe el maestro de ese contexto**.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

#: Estados del maestro que significan "este proveedor ya no opera".
INACTIVE_STATUSES: frozenset[str] = frozenset({"INACTIVE", "REJECTED"})


def normalize_supplier_text(value: str) -> str:
    """Idéntica a `supplier_repository.normalize_name`.

    Se repite aquí en lugar de importarla de `infrastructure/` porque la capa de
    aplicación no debe depender de un repositorio concreto; que sean la misma
    función es un CONTRATO, y lo fija
    `test_the_search_normalizes_exactly_like_the_master_persists`.
    """
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


@dataclass(frozen=True)
class SupplierSelectionDTO:
    supplier_id: str
    supplier_code: str
    legal_name: str
    trade_name: str
    tax_identifier: str | None
    status: str
    risk_level: str | None
    rating_grade: str | None
    #: Bloqueos VIGENTES (`supplier_blocks`), proyectados por separado porque el
    #: selector de Compras los explica con mensajes distintos. Se proyectan
    #: aunque un preset los filtre: el módulo tiene que poder ENSEÑAR que un
    #: proveedor está bloqueado, no sólo esconderlo.
    purchasing_blocked: bool = False
    payment_blocked: bool = False

    @property
    def label(self) -> str:
        """Lo que ve el usuario en un selector."""
        nombre = self.trade_name or self.legal_name
        return f"{self.supplier_code} · {nombre}" if self.supplier_code else nombre


@dataclass(frozen=True)
class EmptySupplierReason:
    """Causa de un resultado vacío, apta para mostrarse al usuario."""
    code: str
    message: str


@dataclass(frozen=True)
class SupplierSearchQuery:
    """Contrato único de búsqueda de proveedores."""

    text: str | None = None
    supplier_code: str | None = None
    tax_identifier: str | None = None

    status: str | None = None
    category: str | None = None
    risk_level: str | None = None
    rating: str | None = None

    #: Sólo proveedores operativos (excluye INACTIVE/REJECTED).
    active_only: bool = False
    #: Sólo proveedores con los que se PUEDE comprar hoy: estado ACTIVE y sin
    #: bloqueo de compras vigente. Es una restricción más fuerte que
    #: `active_only`, no un sinónimo.
    purchasable_only: bool = False

    page: int = 1
    page_size: int = 50

    def __post_init__(self) -> None:
        if int(self.page) < 1:
            raise ValueError("page empieza en 1")
        if int(self.page_size) < 1:
            raise ValueError("page_size debe ser positivo")

    @property
    def limit(self) -> int:
        return int(self.page_size)

    @property
    def offset(self) -> int:
        return (int(self.page) - 1) * int(self.page_size)

    def restrict(self, **overrides) -> "SupplierSearchQuery":
        """Añadir restricciones — la única forma en que un módulo especializa la
        búsqueda. Los flags booleanos sólo se encienden, nunca se apagan: un
        preset no puede relajar lo que otro ya exigió."""
        merged = dict(overrides)
        for flag in ("active_only", "purchasable_only"):
            if flag in merged:
                merged[flag] = bool(getattr(self, flag)) or bool(merged[flag])
        return replace(self, **merged)


#: Columnas del maestro, EN ORDEN, con el literal a usar si no existen. El orden
#: es contrato: `_row_to_dto` indexa por posición, así que lo nuevo va al final.
#: Hay bases y fixtures con un `supplier_master` reducido; seleccionar una
#: columna inexistente lanza `OperationalError` y el consumidor lo atrapa
#: devolviendo `[]` — búsqueda vacía en silencio, peor que un error visible.
_COLUMN_ORDER = (
    ("id", "NULL"), ("supplier_code", "''"), ("legal_name", "''"),
    ("trade_name", "''"), ("tax_identifier", "NULL"), ("status", "''"),
    ("risk_level", "NULL"), ("rating_grade", "NULL"),
)

#: Bloqueos que impiden COMPRAR. `GENERAL_BLOCK` bloquea todo, y `PAYMENT_BLOCK`
#: entra a propósito: en el modelo heredado `bloqueado_financiero` impedía la
#: compra (lo rechazaba `require_eligible`), y dejarlo fuera aquí habría
#: permitido en silencio comprar a proveedores a los que no se les puede pagar.
#: Preservar esa regla no es conservadurismo: comprar a quien no puedes pagar es
#: justamente lo que el bloqueo existe para evitar.
_PURCHASING_BLOCK_TYPES = ("PURCHASING_BLOCK", "GENERAL_BLOCK", "PAYMENT_BLOCK")
#: Los que el selector etiqueta como "Compras deshabilitadas" (no financieros).
_PURCHASING_ONLY_TYPES = ("PURCHASING_BLOCK", "GENERAL_BLOCK")
_PAYMENT_TYPES = ("PAYMENT_BLOCK",)


def _block_exists(types: tuple[str, ...]) -> str:
    return (
        "EXISTS (SELECT 1 FROM supplier_blocks b WHERE b.supplier_id=m.id"
        " AND b.active=1"
        f" AND b.block_type IN ({','.join('?' * len(types))})"
        " AND (b.expires_at IS NULL OR b.expires_at='' OR b.expires_at > datetime('now')))"
    )


_BLOCK_EXISTS = _block_exists(_PURCHASING_BLOCK_TYPES)


def _row_to_dto(r) -> SupplierSelectionDTO:
    return SupplierSelectionDTO(
        supplier_id=str(r[0]), supplier_code=str(r[1] or ""),
        legal_name=str(r[2] or ""), trade_name=str(r[3] or ""),
        tax_identifier=r[4], status=str(r[5] or ""),
        risk_level=r[6], rating_grade=r[7],
        purchasing_blocked=bool(r[8]), payment_blocked=bool(r[9]))


class _BaseSupplierSearch:
    """Constructor único del SQL. Las subclases sólo declaran restricciones."""

    #: Restricciones que el preset impone SIEMPRE, se pidan o no.
    preset_active_only: bool = False
    preset_purchasable_only: bool = False

    def __init__(self, connection) -> None:
        self._conn = connection
        self._columns_cache: set[str] | None = None
        self._blocks_available: bool | None = None

    # ── introspección ────────────────────────────────────────────────────
    def _columns(self) -> set[str]:
        if self._columns_cache is None:
            self._columns_cache = {
                str(r[1]) for r in
                self._conn.execute("PRAGMA table_info(supplier_master)").fetchall()}
        return self._columns_cache

    def _has_blocks_table(self) -> bool:
        """`supplier_blocks` pertenece al mismo esquema, pero hay fixtures que
        sólo crean `supplier_master`. Sin la tabla no hay bloqueos que aplicar,
        y eso NO puede reventar la búsqueda."""
        if self._blocks_available is None:
            self._blocks_available = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table'"
                " AND name='supplier_blocks' LIMIT 1").fetchone() is not None
        return self._blocks_available

    def _projection(self) -> tuple[str, list]:
        cols = self._columns()
        campos = [f"m.{n}" if n in cols else d for n, d in _COLUMN_ORDER]
        if self._has_blocks_table():
            campos.append(_block_exists(_PURCHASING_ONLY_TYPES))
            campos.append(_block_exists(_PAYMENT_TYPES))
            return (", ".join(campos),
                    list(_PURCHASING_ONLY_TYPES) + list(_PAYMENT_TYPES))
        campos.extend(("0", "0"))
        return ", ".join(campos), []

    # ── preset ───────────────────────────────────────────────────────────
    def _preset(self, criteria: SupplierSearchQuery) -> SupplierSearchQuery:
        overrides: dict = {}
        if self.preset_active_only:
            overrides["active_only"] = True
        if self.preset_purchasable_only:
            overrides["purchasable_only"] = True
        return criteria.restrict(**overrides) if overrides else criteria

    # ── API ──────────────────────────────────────────────────────────────
    def search(self, criteria: SupplierSearchQuery | None = None,
               **legacy) -> list[SupplierSelectionDTO]:
        """Acepta el contrato o los kwargs históricos (`query`/`limit`/`offset`).

        Los kwargs siguen vivos porque el presentador de Proveedores y el de
        Compras ya llamaban así; es la misma consulta por dentro, no una segunda
        ruta.
        """
        if criteria is not None and legacy:
            raise TypeError("Use SupplierSearchQuery o kwargs, no ambos")
        criteria = self._preset(criteria if criteria is not None
                                else _from_legacy_kwargs(**legacy))
        sql, params = self._build(criteria, limit=criteria.limit,
                                  offset=criteria.offset)
        return [_row_to_dto(r) for r in self._conn.execute(sql, params).fetchall()]

    def count(self, criteria: SupplierSearchQuery | None = None, **legacy) -> int:
        if criteria is not None and legacy:
            raise TypeError("Use SupplierSearchQuery o kwargs, no ambos")
        criteria = self._preset(criteria if criteria is not None
                                else _from_legacy_kwargs(**legacy))
        where, params = self._where(criteria)
        sql = "SELECT COUNT(*) FROM supplier_master m"
        if where:
            sql += " WHERE " + " AND ".join(where)
        fila = self._conn.execute(sql, params).fetchone()
        return int(fila[0]) if fila else 0

    def is_purchasable(self, supplier_id: str) -> bool:
        """¿Se puede comprar HOY a este proveedor?

        UNA sola definición de "comprable", compartida por la puerta de guardado
        (`SupplierDirectoryQueryService.require_eligible`) y por cualquier
        pantalla que quiera filtrar. Tenerla dos veces es como empezó todo esto:
        el selector ofrecía lo que la puerta después rechazaba.
        """
        supplier_id = str(supplier_id or "").strip()
        if not supplier_id:
            return False
        criteria = SupplierSearchQuery(purchasable_only=True, page_size=1)
        where, params = self._where(criteria)
        where.append("m.id=?")
        params.append(supplier_id)
        sql = "SELECT 1 FROM supplier_master m WHERE " + " AND ".join(where) + " LIMIT 1"
        return self._conn.execute(sql, params).fetchone() is not None

    def exists(self, supplier_id: str) -> bool:
        """Distinguir "no existe" de "existe pero no puede comprar" — son dos
        mensajes distintos para quien opera."""
        supplier_id = str(supplier_id or "").strip()
        if not supplier_id:
            return False
        return self._conn.execute(
            "SELECT 1 FROM supplier_master WHERE id=? LIMIT 1",
            (supplier_id,)).fetchone() is not None

    def explain_empty(self, criteria: SupplierSearchQuery | None = None,
                      **legacy) -> EmptySupplierReason | None:
        """Por qué una búsqueda no devolvió nada.

        Cero resultados tiene causas muy distintas —no hay proveedores, ninguno
        está aprobado todavía, los que hay están bloqueados para comprar, o el
        término simplemente no coincide— y presentarlas todas como "Sin
        resultados" deja al usuario sin saber qué hacer. Relaja el criterio por
        pasos, con el MISMO constructor de SQL. `None` significa que sí hay.
        """
        base = self._preset(criteria if criteria is not None
                            else _from_legacy_kwargs(**legacy))

        def hay(c: SupplierSearchQuery) -> bool:
            sql, params = self._build(c, limit=1, offset=0)
            return self._conn.execute(sql, params).fetchone() is not None

        if hay(base):
            return None
        sin_texto = {"text": None, "supplier_code": None, "tax_identifier": None}
        pasos = [
            (replace(base, **sin_texto), "NO_COINCIDE",
             "Hay proveedores disponibles, pero ninguno coincide con la búsqueda."),
        ]
        # Este peldaño sólo tiene sentido si alguien exigió "comprable"; si no,
        # repetiría exactamente la consulta anterior y leería como si probara
        # algo que no prueba.
        if base.purchasable_only:
            pasos.append(
                (replace(base, **sin_texto, purchasable_only=False),
                 "BLOQUEADOS_PARA_COMPRAS",
                 "Los proveedores que hay están bloqueados para compras. "
                 "Revísalo en Proveedores → ficha → Riesgo y evaluación."))
        pasos.append(
            (replace(base, **sin_texto, purchasable_only=False, active_only=False,
                     status=None), "SIN_APROBAR",
             "Hay proveedores capturados, pero ninguno está activo todavía "
             "(borrador, pendiente de aprobación o dado de baja)."))
        for criterio, codigo, mensaje in pasos:
            if hay(criterio):
                return EmptySupplierReason(codigo, mensaje)
        return EmptySupplierReason(
            "SIN_PROVEEDORES", "Todavía no hay proveedores dados de alta.")

    # ── interno ──────────────────────────────────────────────────────────
    def _where(self, criteria: SupplierSearchQuery) -> tuple[list[str], list]:
        cols = self._columns()
        where: list[str] = []
        params: list = []

        if criteria.text:
            partes: list[str] = []
            crudo = f"%{str(criteria.text).strip()}%"
            # El normalizado va PRIMERO porque es el que tolera acentos,
            # puntuación y espacios de más; los LIKE crudos son el respaldo
            # para filas viejas con el normalizado vacío (default del esquema).
            if "normalized_name" in cols:
                normalizado = normalize_supplier_text(criteria.text)
                if normalizado:
                    partes.append("m.normalized_name LIKE ?")
                    params.append(f"%{normalizado}%")
            for columna in ("legal_name", "trade_name", "supplier_code",
                            "tax_identifier"):
                if columna in cols:
                    partes.append(f"COALESCE(m.{columna},'') LIKE ?")
                    params.append(crudo)
            if partes:
                where.append("(" + " OR ".join(partes) + ")")

        if criteria.supplier_code and "supplier_code" in cols:
            where.append("m.supplier_code=?")
            params.append(str(criteria.supplier_code).strip())
        if criteria.tax_identifier and "tax_identifier" in cols:
            where.append("m.tax_identifier=?")
            params.append(str(criteria.tax_identifier).strip().upper())

        if criteria.status and "status" in cols:
            where.append("m.status=?")
            params.append(str(criteria.status))
        if criteria.purchasable_only and "status" in cols:
            where.append("m.status='ACTIVE'")
        elif criteria.active_only and "status" in cols:
            marcadores = ",".join("?" * len(INACTIVE_STATUSES))
            where.append(f"m.status NOT IN ({marcadores})")
            params.extend(sorted(INACTIVE_STATUSES))

        if criteria.purchasable_only and self._has_blocks_table():
            where.append("NOT " + _BLOCK_EXISTS)
            params.extend(_PURCHASING_BLOCK_TYPES)

        if criteria.risk_level and "risk_level" in cols:
            where.append("m.risk_level=?")
            params.append(str(criteria.risk_level))
        if criteria.rating and "rating_grade" in cols:
            where.append("m.rating_grade=?")
            params.append(str(criteria.rating))
        if criteria.category:
            where.append("EXISTS (SELECT 1 FROM supplier_category_links l"
                         " WHERE l.supplier_id=m.id AND l.category_code=?)")
            params.append(str(criteria.category))
        return where, params

    def _build(self, criteria: SupplierSearchQuery, *, limit: int,
               offset: int) -> tuple[str, list]:
        proyeccion, proyeccion_params = self._projection()
        where, where_params = self._where(criteria)
        sql = f"SELECT {proyeccion} FROM supplier_master m"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY m.legal_name LIMIT ? OFFSET ?"
        return sql, proyeccion_params + where_params + [int(limit), int(offset)]


def _from_legacy_kwargs(*, query: str | None = None, status: str | None = None,
                        category: str | None = None, risk_level: str | None = None,
                        rating: str | None = None, limit: int = 50,
                        offset: int = 0) -> SupplierSearchQuery:
    """Traduce la firma histórica (`query`/`limit`/`offset`) al contrato."""
    tamano = max(int(limit), 1)
    pagina = (int(offset) // tamano) + 1
    return SupplierSearchQuery(
        text=query, status=status, category=category, risk_level=risk_level,
        rating=rating, page=pagina, page_size=tamano)


class SupplierDirectorySearchQueryService(_BaseSupplierSearch):
    """Sin preset: el directorio completo del maestro.

    Para el módulo de Proveedores, que existe justamente para ver borradores,
    pendientes de aprobación, suspendidos y dados de baja. Filtrarlos aquí
    dejaría sin pantalla al trabajo de aprobar.
    """


class SearchProcurementSuppliersQueryService(_BaseSupplierSearch):
    """Compras: proveedores vigentes, INCLUIDOS los bloqueados.

    Deliberadamente NO usa `purchasable_only`. El selector de Compras ya
    enseñaba los bloqueados con un subtítulo que lo explica ("Bloqueado
    financieramente", "Compras deshabilitadas") en vez de esconderlos, y esa
    decisión es buena: al comprador le sirve más ver el proveedor con el motivo
    que no verlo y no saber por qué falta. Esconderlos habría cambiado el
    comportamiento en silencio.

    Por eso el DTO proyecta `purchasing_blocked`: la pantalla necesita el dato
    para etiquetarlo. Quien sí tiene que filtrar es la puerta de guardado
    (`is_purchasable`), no el selector.

    El preset se queda en `active_only`, que excluye lo que ya no opera
    (dados de baja y rechazados): eso no es un bloqueo reversible, es un
    proveedor que dejó de existir para el negocio.
    """
    preset_active_only = True
