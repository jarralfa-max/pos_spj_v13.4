"""Búsqueda canónica de productos (§11) — UN solo contrato, presets por módulo.

Antes había un buscador por módulo (Compras, Inventario, Merma, Precios…), cada
uno con su propio SQL y su propia idea de qué es "coincide": uno filtraba por
`p.name LIKE`, otro por `name_normalized`, otro leía columnas que no existen. El
mismo texto devolvía resultados distintos según la pantalla.

Ahora hay **una** consulta, `ProductSearchQuery`, y **un** constructor de SQL.
Cada módulo sólo AÑADE restricciones sobre ese contrato:

    Ventas          -> active + sellable + branch (+ canal)
    Compras         -> active + purchasable
    Transferencias  -> active + inventariable + sucursal origen
    Precios         -> active
    Inventario      -> active + inventariable + branch

Las subclases de abajo son exactamente eso: presets de restricciones. No tienen
SQL propio.

LÍMITE DE CONTEXTO (§30, §37): Productos NUNCA consulta tablas de balance de
Inventario. Por eso `with_stock_only` no es un JOIN a `inventory_balances` — se
resuelve por un puerto inyectado (`stock_port`), que la composición satisface
con el servicio de disponibilidad de Inventario. Sin puerto, pedir
`with_stock_only` es un error ruidoso, no un filtro que se ignora en silencio.

NORMALIZACIÓN — ojo con los acentos: el maestro guarda `name_normalized` con
`product_master_use_cases._normalized`, que baja a minúsculas y colapsa espacios
pero **no** pliega acentos (a diferencia del value object
`ProductName.normalize_name`, cuyo resultado se descarta al persistir). Este
módulo normaliza el texto de búsqueda EXACTAMENTE igual para poder comparar
contra lo almacenado; plegar acentos aquí sólo produciría cero coincidencias.
Que "jalapeno" no encuentre "Jalapeño" es un defecto del lado de escritura, y se
corrige ahí, no falseando la comparación aquí.
"""

from __future__ import annotations

import sqlite3

from dataclasses import dataclass, replace
from typing import Protocol


@dataclass(frozen=True)
class ProductSelectionDTO:
    product_id: str
    code: str
    name: str
    short_name: str | None
    product_type: str
    base_unit_id: str | None
    species_id: str | None
    catch_weight_enabled: bool
    lot_controlled: bool
    inventory_managed: bool
    sellable: bool
    purchasable: bool
    producible: bool
    internal_only: bool
    #: Estado de ciclo de vida del maestro. Lo necesita el LISTADO del catálogo
    #: (que existe para ver borradores y productos en revisión); los selectores
    #: normalmente filtran con `active_only` y no lo miran.
    lifecycle_status: str = ""


@dataclass(frozen=True)
class EmptyResultReason:
    """Causa de un resultado vacío, apta para mostrarse al usuario."""
    code: str
    message: str


class ProductStockPort(Protocol):
    """Lo que Productos necesita de Inventario para `with_stock_only`, sin
    conocer sus tablas. `InventoryAvailabilityQueryService` ya lo cumple tal
    cual: se inyecta directo, sin adaptador."""

    def get_availability(self, *, product_id: str, branch_id: str,
                         warehouse_id: str | None = None): ...


def normalize_search_text(value: str) -> str:
    """Misma forma que el maestro persiste en `name_normalized`.

    Deliberadamente idéntica a `product_master_use_cases._normalized`,
    incluyendo que NO quita acentos — ver la nota del docstring del módulo.
    """
    return " ".join(str(value or "").strip().lower().split())


@dataclass(frozen=True)
class ProductSearchQuery:
    """Contrato único de búsqueda de productos.

    `sku` es el `code` del maestro: aquí no existe una columna `sku` aparte, y
    inventar una sería un segundo identificador para lo mismo.
    """

    text: str | None = None
    barcode: str | None = None
    sku: str | None = None

    branch_id: str | None = None
    channel_id: str | None = None
    warehouse_id: str | None = None

    product_type: str | None = None
    species_id: str | None = None
    category_id: str | None = None

    active_only: bool = True
    sellable_only: bool = False
    purchasable_only: bool = False
    inventory_managed_only: bool = False
    producible_only: bool = False
    exclude_internal: bool = False
    with_stock_only: bool = False

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

    def restrict(self, **overrides) -> "ProductSearchQuery":
        """Añadir restricciones — la única forma en que un módulo especializa
        la búsqueda. Los flags booleanos sólo se encienden, nunca se apagan:
        un preset no puede relajar lo que otro ya exigió."""
        merged = dict(overrides)
        for flag in ("active_only", "sellable_only", "purchasable_only",
                     "inventory_managed_only", "producible_only",
                     "exclude_internal", "with_stock_only"):
            if flag in merged:
                merged[flag] = bool(getattr(self, flag)) or bool(merged[flag])
        return replace(self, **merged)


#: Columnas del maestro, EN ORDEN, con el literal que se usa cuando la columna
#: no existe en la base. El orden es contrato: `_row_to_dto` indexa por
#: posición, así que las entradas nuevas van al final y nunca se reordenan.
#:
#: Por qué hay literales: hay bases antiguas y bastantes fixtures que crean un
#: `products` reducido (a veces sólo `id`/`base_unit_id`). Seleccionar una
#: columna inexistente lanza `OperationalError`, y el consumidor vivo de esto
#: —`InventoryPresenter.product_options`— lo atrapa y devuelve `[]`: búsqueda
#: vacía en silencio, que es peor que un error visible. Se degrada, no revienta.
_COLUMN_ORDER = (
    ("id", "NULL"), ("code", "NULL"), ("name", "NULL"), ("short_name", "NULL"),
    ("product_type", "NULL"), ("base_unit_id", "NULL"), ("species_id", "NULL"),
    ("catch_weight_enabled", "0"), ("lot_controlled", "0"),
    ("inventory_managed", "0"), ("sellable", "0"), ("purchasable", "0"),
    ("producible", "0"), ("internal_only", "0"), ("lifecycle_status", "NULL"),
)

#: Tope de filas a inspeccionar cuando `with_stock_only` obliga a filtrar fuera
#: del SQL. Paginar en la base y filtrar después devolvería páginas cortas sin
#: avisar; se prefiere un tope explícito y visible.
_STOCK_SCAN_CAP = 2000

_CAPABILITY_FLAGS = {
    "sellable_only": "sellable",
    "purchasable_only": "purchasable",
    "inventory_managed_only": "inventory_managed",
    "producible_only": "producible",
}


def _row_to_dto(r) -> ProductSelectionDTO:
    return ProductSelectionDTO(
        product_id=r[0], code=r[1], name=r[2], short_name=r[3], product_type=r[4],
        base_unit_id=r[5], species_id=r[6], catch_weight_enabled=bool(r[7]),
        lot_controlled=bool(r[8]), inventory_managed=bool(r[9]), sellable=bool(r[10]),
        purchasable=bool(r[11]), producible=bool(r[12]), internal_only=bool(r[13]),
        lifecycle_status=str(r[14] or ""))


class _BaseProductSearch:
    """Constructor único del SQL. Las subclases sólo declaran restricciones."""

    #: Capacidad exigida por el preset: 'sellable'|'purchasable'|
    #: 'inventory_managed'|'producible'|None
    capability_column: str | None = None
    #: Excluir productos de uso interno (POS)
    exclude_internal: bool = False

    def __init__(self, connection, *, stock_port: ProductStockPort | None = None) -> None:
        self._conn = connection
        self._stock_port = stock_port
        self._barcodes_available: bool | None = None
        self._product_columns: set[str] | None = None

    def _columns(self) -> set[str]:
        """Columnas que `products` tiene DE VERDAD en esta base. Se consulta una
        vez por instancia."""
        if self._product_columns is None:
            self._product_columns = {
                str(r[1]) for r in
                self._conn.execute("PRAGMA table_info(products)").fetchall()}
        return self._product_columns

    def _has_normalized_column(self) -> bool:
        """Sin `name_normalized` se busca por `p.name`/`p.code`, que es
        exactamente lo que hacía el buscador anterior: degradar, nunca reventar."""
        return "name_normalized" in self._columns()

    def _projection(self) -> str:
        """`SELECT` acotado a lo que existe; el resto entra como literal para
        que las posiciones de `_row_to_dto` no se muevan nunca."""
        cols = self._columns()
        return ", ".join(f"p.{nombre}" if nombre in cols else defecto
                         for nombre, defecto in _COLUMN_ORDER)

    def _has_barcodes_table(self) -> bool:
        """`product_barcodes` pertenece al mismo esquema de Productos, pero hay
        fixtures y bases antiguas que sólo tienen `products`. La búsqueda por
        texto no puede reventar por eso: antes no tocaba esta tabla y funcionaba.
        Se comprueba una vez por instancia."""
        if self._barcodes_available is None:
            fila = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='product_barcodes' LIMIT 1").fetchone()
            self._barcodes_available = fila is not None
        return self._barcodes_available

    # ── preset ───────────────────────────────────────────────────────────
    def enabled_in_branch(self, product_ids, branch_id: str) -> set[str] | None:
        """Cuáles de ``product_ids`` están habilitados en ``branch_id``
        (``branch_product``). Para contextos que buscan en el catálogo GLOBAL y
        sólo INFORMAN la habilitación (Compras). ``None`` = no se puede saber
        (sin tabla): quien llama no debe marcar nada."""
        ids = [str(pid) for pid in product_ids if pid]
        if not ids or not branch_id:
            return set()
        marks = ",".join("?" * len(ids))
        try:
            rows = self._conn.execute(
                f"SELECT product_id FROM branch_product WHERE branch_id=? AND enabled=1"
                f" AND product_id IN ({marks})", [str(branch_id), *ids]).fetchall()
        except sqlite3.OperationalError:
            return None
        return {str(r[0]) for r in rows}

    def _preset(self, criteria: "ProductSearchQuery") -> "ProductSearchQuery":
        overrides: dict = {}
        if self.exclude_internal:
            overrides["exclude_internal"] = True
        for flag, column in _CAPABILITY_FLAGS.items():
            if self.capability_column == column:
                overrides[flag] = True
        return criteria.restrict(**overrides) if overrides else criteria

    # ── API ──────────────────────────────────────────────────────────────
    def search(self, criteria: "ProductSearchQuery | None" = None,
               **legacy) -> list[ProductSelectionDTO]:
        """Acepta el contrato (`ProductSearchQuery`) o los kwargs históricos.

        Los kwargs siguen vivos porque siete consumidores ya llaman así; es la
        misma consulta por dentro, no una segunda ruta.
        """
        if criteria is not None and legacy:
            raise TypeError("Use ProductSearchQuery o kwargs, no ambos")
        criteria = self._preset(criteria if criteria is not None
                                else _from_legacy_kwargs(**legacy))

        if criteria.with_stock_only:
            return self._search_with_stock(criteria)
        sql, params = self._build(criteria, limit=criteria.limit,
                                  offset=criteria.offset)
        return [_row_to_dto(r) for r in self._conn.execute(sql, params).fetchall()]

    # ── interno ──────────────────────────────────────────────────────────
    def _search_with_stock(self, criteria: "ProductSearchQuery") -> list[ProductSelectionDTO]:
        if self._stock_port is None:
            raise ValueError(
                "with_stock_only requiere inyectar stock_port: Productos no "
                "consulta balances de Inventario (§30/§37)")
        if not criteria.branch_id:
            raise ValueError("with_stock_only requiere branch_id")
        sql, params = self._build(criteria, limit=_STOCK_SCAN_CAP, offset=0)
        con_stock: list[ProductSelectionDTO] = []
        for row in self._conn.execute(sql, params).fetchall():
            dto = _row_to_dto(row)
            saldo = self._stock_port.get_availability(
                product_id=dto.product_id, branch_id=criteria.branch_id,
                warehouse_id=criteria.warehouse_id)
            if getattr(saldo, "available", 0) > 0:
                con_stock.append(dto)
        inicio = criteria.offset
        return con_stock[inicio:inicio + criteria.limit]

    def explain_empty(self, criteria: "ProductSearchQuery | None" = None,
                      **legacy) -> "EmptyResultReason | None":
        """Por qué una búsqueda no devolvió nada.

        Cero resultados tiene causas muy distintas —catálogo vacío, nada
        activo, nada habilitado en esta sucursal, o simplemente que el término
        no coincide— y presentarlas todas como "Sin resultados" es la misma
        mentira silenciosa que §35 prohíbe para los fallos técnicos. Relaja el
        criterio por pasos (mismo constructor de SQL, sin rutas nuevas) y
        devuelve la primera causa que explica el vacío; `None` significa que sí
        hay resultados.
        """
        base = self._preset(criteria if criteria is not None
                            else _from_legacy_kwargs(**legacy))

        def hay(c: "ProductSearchQuery") -> bool:
            sql, params = self._build(c, limit=1, offset=0)
            return self._conn.execute(sql, params).fetchone() is not None

        sin_texto = {"text": None, "barcode": None, "sku": None}
        if hay(base):
            # `_build` no evalúa existencia (se resuelve por puerto), así que si
            # el SQL sí trae filas y el vacío venía de `with_stock_only`, la
            # causa es justamente ésa.
            if base.with_stock_only:
                return EmptyResultReason(
                    "SIN_EXISTENCIA",
                    "Hay productos que coinciden, pero ninguno tiene existencia "
                    "en esta sucursal.")
            return None

        # Primero se relaja MANTENIENDO el texto: si lo buscado existe pero no
        # está habilitado aquí (o no está activo), ésa es la causa. Relajar antes
        # el texto decía "ninguno coincide" en cuanto la sucursal tenía cualquier
        # otro producto habilitado — medido 2026-09-25: «pechuga» en una sucursal
        # con sólo «Alas» habilitado respondía "no coincide".
        con_texto = (
            (replace(base, branch_id=None, channel_id=None), "SIN_HABILITAR_EN_SUCURSAL",
             "Lo que buscas existe, pero no está habilitado en esta sucursal. "
             "Habilítalo en Productos → Sucursales y surtidos."),
            (replace(base, branch_id=None, channel_id=None, active_only=False), "SIN_ACTIVOS",
             "Lo que buscas existe, pero todavía no está activo (borrador o en revisión)."),
        )
        if any(getattr(base, campo) for campo in sin_texto):
            for criterio, codigo, mensaje in con_texto:
                if hay(criterio):
                    return EmptyResultReason(codigo, mensaje)

        pasos = (
            (replace(base, **sin_texto), "NO_COINCIDE",
             "Hay productos disponibles, pero ninguno coincide con la búsqueda."),
            (replace(base, **sin_texto, branch_id=None, channel_id=None),
             "SIN_HABILITAR_EN_SUCURSAL",
             "Hay productos, pero ninguno está habilitado en esta sucursal. "
             "Habilítalos en Productos → Sucursales y surtidos."),
            (replace(base, **sin_texto, branch_id=None, channel_id=None,
                     active_only=False), "SIN_ACTIVOS",
             "Los productos existentes todavía no están activos "
             "(borrador o en revisión)."),
        )
        for criterio, codigo, mensaje in pasos:
            if hay(criterio):
                return EmptyResultReason(codigo, mensaje)
        return EmptyResultReason(
            "SIN_CATALOGO", "No hay productos en el catálogo para este módulo.")

    def _build(self, criteria: "ProductSearchQuery", *, limit: int,
               offset: int) -> tuple[str, list]:
        joins: list[str] = []
        join_params: list = []
        where: list[str] = []
        where_params: list = []

        # Un filtro sobre una columna que no existe no puede aplicarse. Se omite
        # (el esquema es anterior al concepto) en vez de reventar la consulta:
        # para un selector, devolver de más es mucho menos dañino que no
        # devolver nada, y es además lo que hacía el buscador al que sustituye.
        cols = self._columns()
        for flag, column in _CAPABILITY_FLAGS.items():
            if getattr(criteria, flag) and column in cols:
                where.append(f"p.{column}=1")
        if criteria.exclude_internal and "internal_only" in cols:
            where.append("p.internal_only=0")
        if criteria.active_only and "lifecycle_status" in cols:
            where.append("p.lifecycle_status='ACTIVE'")

        # habilitación por sucursal (branch_product)
        if criteria.branch_id:
            joins.append("JOIN branch_product bp ON bp.product_id=p.id "
                         "AND bp.branch_id=? AND bp.enabled=1")
            join_params.append(str(criteria.branch_id))
        # surtido por canal (assortment activo del canal que contiene el producto)
        if criteria.channel_id:
            join = ("JOIN assortment_products ap ON ap.product_id=p.id AND ap.enabled=1 "
                    "JOIN assortments a ON a.id=ap.assortment_id AND a.active=1 "
                    "AND a.channel=?")
            join_params.append(str(criteria.channel_id))
            if criteria.branch_id:
                join += " AND (a.branch_id=? OR a.branch_id='')"
                join_params.append(str(criteria.branch_id))
            joins.append(join)

        if criteria.text:
            # `name` además de `name_normalized` a propósito: hay filas viejas
            # con el normalizado vacío (default del esquema), y perderlas sería
            # una regresión frente al buscador anterior, que miraba `p.name`.
            needle = f"%{normalize_search_text(criteria.text)}%"
            crudo = f"%{str(criteria.text).strip()}%"
            partes: list[str] = []
            if self._has_normalized_column():
                partes.append("p.name_normalized LIKE ?")
                where_params.append(needle)
            if "name" in cols:
                partes.append("p.name LIKE ?")
                where_params.append(crudo)
            if "code" in cols:
                partes.append("COALESCE(p.code,'') LIKE ?")
                where_params.append(crudo)
            if self._has_barcodes_table():
                partes.append("EXISTS (SELECT 1 FROM product_barcodes b "
                              "WHERE b.product_id=p.id AND b.active=1 "
                              "AND b.barcode_value LIKE ?)")
                where_params.append(crudo)
            where.append("(" + " OR ".join(partes) + ")")
        if criteria.barcode:
            # Exacto: un escáner no quiere coincidencias parciales.
            if self._has_barcodes_table():
                where.append("EXISTS (SELECT 1 FROM product_barcodes b "
                             "WHERE b.product_id=p.id AND b.active=1 "
                             "AND b.barcode_value=?)")
                where_params.append(str(criteria.barcode).strip())
            else:
                # Sin índice de códigos no hay forma de satisfacer el criterio.
                # Ignorarlo devolvería el catálogo entero ante un escaneo.
                where.append("1=0")
        if criteria.sku:
            where.append("p.code=?")
            where_params.append(str(criteria.sku).strip())
        if criteria.product_type and "product_type" in cols:
            where.append("p.product_type=?")
            where_params.append(str(criteria.product_type))
        if criteria.species_id and "species_id" in cols:
            where.append("p.species_id=?")
            where_params.append(str(criteria.species_id))
        if criteria.category_id and "category_id" in cols:
            where.append("p.category_id=?")
            where_params.append(str(criteria.category_id))

        sql = f"SELECT DISTINCT {self._projection()} FROM products p " + " ".join(joins)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.name LIMIT ? OFFSET ?"
        return sql, join_params + where_params + [int(limit), int(offset)]


def _from_legacy_kwargs(*, query: str | None = None, branch_id: str | None = None,
                        channel_id: str | None = None, warehouse_id: str | None = None,
                        product_type: str | None = None, species_id: str | None = None,
                        category_id: str | None = None, active_only: bool = True,
                        limit: int = 50, offset: int = 0) -> ProductSearchQuery:
    """Traduce la firma histórica (`query`/`limit`/`offset`) al contrato."""
    tamano = max(int(limit), 1)
    pagina = (int(offset) // tamano) + 1
    return ProductSearchQuery(
        text=query, branch_id=branch_id, channel_id=channel_id,
        warehouse_id=warehouse_id, product_type=product_type, species_id=species_id,
        category_id=category_id, active_only=active_only,
        page=pagina, page_size=tamano)


class ProductCatalogSearchQueryService(_BaseProductSearch):
    """Sin preset: el catálogo completo del maestro. Para consumidores cuya
    única restricción es la que traen en el `ProductSearchQuery` (p. ej.
    Precios: sólo `active`)."""


class SearchSellableProductsQueryService(_BaseProductSearch):
    """POS/venta: ACTIVE, vendibles, no internos, habilitados en la
    sucursal/canal indicados."""
    capability_column = "sellable"
    exclude_internal = True


class SearchPurchasableProductsQueryService(_BaseProductSearch):
    """Compras: ACTIVE, comprables, habilitados en la sucursal."""
    capability_column = "purchasable"


class SearchInventoryManagedProductsQueryService(_BaseProductSearch):
    """Inventario: productos que controlan inventario físico."""
    capability_column = "inventory_managed"


class SearchTransferableProductsQueryService(_BaseProductSearch):
    """Transferencias: inventariables habilitados en la sucursal origen.

    El destino se valida en el flujo de transferencias (unidad compatible +
    destino habilitado); aquí se filtra el catálogo transferible del origen."""
    capability_column = "inventory_managed"


class SearchProductionInputsQueryService(_BaseProductSearch):
    """Producción: insumos producibles/procesables (input de receta/rendimiento)."""
    capability_column = "inventory_managed"


class SearchWasteEligibleProductsQueryService(_BaseProductSearch):
    """Merma: productos inventariables sujetos a merma administrativa."""
    capability_column = "inventory_managed"
