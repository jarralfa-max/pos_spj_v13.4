"""Transaction boundary helpers for application services and use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Transaction:
    """Small DB-API transaction wrapper.

    UI code must not use this directly. Use cases should receive a UnitOfWork
    abstraction that owns this transaction boundary.
    """

    connection: Any
    _completed: bool = False

    def commit(self) -> None:
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        self.connection.rollback()
        self._completed = True

    def close(self) -> None:
        close = getattr(self.connection, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "Transaction":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object) -> None:
        if exc_type is None and not self._completed:
            self.commit()
        elif exc_type is not None and not self._completed:
            self.rollback()
        self.close()


# ── Frontera transaccional de las unidades de trabajo (ADR-006, Slice 0) ────
#
# Antes cada UoW confiaba en que la conexión abriera la transacción por su
# cuenta. Con la conexión del escritorio (`sqlite3.connect`, transacciones
# implícitas) funcionaba; con el pool en autocommit (`connection.py`) cada
# sentencia se confirmaba sola y `rollback()` no deshacía nada (R-01, medido
# sobre una copia de la base real). Además, una UoW anidada en otra confirmaba
# la transacción de la de afuera a mitad del flujo.
#
# Regla única, independiente del modo de la conexión:
#   - la UoW MÁS EXTERNA de un hilo sobre una conexión es la dueña: abre
#     `BEGIN` si no hay transacción, y confirma o revierte al salir;
#   - una UoW anidada (de cualquier contexto) abre un SAVEPOINT: su éxito lo
#     libera y su falla revierte sólo lo suyo; nunca confirma la de afuera;
#   - `owns_transaction=False`: se une a la transacción de quien llama y no
#     toca la conexión (contrato vigente de Inventario, Ventas, Caja…);
#   - si la UoW externa encuentra una transacción ya abierta por código ajeno
#     a una UoW, la confirma o revierte al salir, como siempre lo hizo.

import threading
from itertools import count

_OPEN_UNITS: dict[tuple[int, int], tuple[Any, int]] = {}
_SAVEPOINT_SEQ = count(1)


def _raw(connection: Any) -> Any:
    """La conexión sqlite3 detrás de un envoltorio (`DatabaseWrapper`)."""
    interna = getattr(connection, "_conn", None)
    return interna if interna is not None else connection


class TransactionalUnitOfWork:
    """Base de las unidades de trabajo por contexto.

    La subclase asigna ``self.connection`` y, si acepta unirse a una
    transacción ajena, ``self._owns_transaction``. Repositorios nunca confirman.
    """

    connection: Any
    _owns_transaction: bool = True
    #: Caja exige que una UoW no se confirme dos veces (CASH-3).
    _reject_double_commit: bool = False

    def __enter__(self):
        self._completed = False
        self._mode = "joined" if not getattr(self, "_owns_transaction", True) else None
        self._savepoint = None
        raw = _raw(self.connection)
        self._key = (id(raw), threading.get_ident())
        holder, depth = _OPEN_UNITS.get(self._key, (raw, 0))
        if holder is not raw:          # id reutilizado por otra conexión
            depth = 0
        if self._mode is None:
            if depth > 0:
                self._mode = "nested"
                self._savepoint = f"uow_{next(_SAVEPOINT_SEQ)}"
                self.connection.execute(f"SAVEPOINT {self._savepoint}")
            elif getattr(raw, "in_transaction", True) is False:
                self.connection.execute("BEGIN")
                self._mode = "owner"
            else:
                self._mode = "inherited"   # transacción abierta fuera de una UoW
        _OPEN_UNITS[self._key] = (raw, depth + 1)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            if exc_type is not None:
                self.rollback()
            elif not self._completed:
                self.commit()
        finally:
            holder, depth = _OPEN_UNITS.get(self._key, (None, 1))
            if depth > 1:
                _OPEN_UNITS[self._key] = (holder, depth - 1)
            else:
                _OPEN_UNITS.pop(self._key, None)
        return False

    @property
    def owns_transaction(self) -> bool:
        return getattr(self, "_mode", None) in ("owner", "inherited", None) and getattr(
            self, "_owns_transaction", True)

    def commit(self) -> None:
        if getattr(self, "_completed", False):
            if self._reject_double_commit:
                raise RuntimeError(f"{type(self).__name__} already completed")
            return
        modo = getattr(self, "_mode", None)
        if modo == "nested":
            self.connection.execute(f"RELEASE SAVEPOINT {self._savepoint}")
        elif modo != "joined" and getattr(self, "_owns_transaction", True):
            # owner / inherited, o una UoW usada sin `with` (contrato anterior).
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        modo = getattr(self, "_mode", None)
        if getattr(self, "_completed", False) and (modo == "nested"
                                                   or self._reject_double_commit):
            return   # el SAVEPOINT ya se liberó / Caja: una UoW se cierra una vez
        if modo == "nested":
            self.connection.execute(f"ROLLBACK TO SAVEPOINT {self._savepoint}")
            self.connection.execute(f"RELEASE SAVEPOINT {self._savepoint}")
        elif modo != "joined" and getattr(self, "_owns_transaction", True):
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
