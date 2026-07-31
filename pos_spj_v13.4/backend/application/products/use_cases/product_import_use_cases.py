"""Use cases de importación de productos (CSV/XLSX) — preview → aprobar → ejecutar.

Flujo en tres pasos con segregación de funciones:
1. **Crear batch** (``IMPORT_EXECUTE``): parsea el archivo, valida cada fila y las
   deja en staging con estado VALID/INVALID (status del job = PREVIEWED). No crea
   productos todavía — sólo la vista previa.
2. **Aprobar** (``IMPORT_APPROVE`` + segregación: el aprobador no puede ser quien
   creó el batch).
3. **Ejecutar** (``IMPORT_EXECUTE``): crea un producto por cada fila VALID vía el
   caso de uso canónico del maestro (código automático si la fila no trae código;
   manual si lo trae, exigiendo el permiso de override). Idempotente por fila: sólo
   se crean las filas aún no creadas.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_import_commands import (
    CreateImportBatchCommand,
    ImportBatchActionCommand,
)
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
)
from backend.domain.products.events import ProductEvents
from backend.domain.products.policies.product_import_policy import validate_import_row
from backend.infrastructure.db.repositories.products.import_repository import (
    ProductImportRepository,
)
from backend.infrastructure.imports import product_import_parser as parser

logger = logging.getLogger("spj.products.import_use_cases")

_MASTER_FIELDS = ("code", "name", "short_name", "description", "product_type",
                  "base_unit_id", "category_id", "brand_id")


@dataclass(frozen=True)
class ImportResult:
    success: bool
    job_id: str | None
    message: str
    total: int = 0
    valid: int = 0
    invalid: int = 0
    created: int = 0


class CreateImportBatchUseCase:
    name = "CreateImportBatchUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductImportRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def execute(self, command: CreateImportBatchCommand) -> ImportResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.IMPORT_EXECUTE)
        try:
            rows = parser.parse(command.filename, command.data)
        except Exception as exc:  # noqa: BLE001 — archivo ilegible → error de UI
            return ImportResult(False, None, f"No se pudo leer el archivo: {exc}")
        if not rows:
            return ImportResult(False, None, "El archivo no tiene filas de datos")

        from backend.shared.ids import new_uuid
        job_id = new_uuid()
        fmt = "XLSX" if command.filename.lower().endswith(".xlsx") else "CSV"
        valid = invalid = 0
        staged = []
        for i, row in enumerate(rows, start=1):
            ok, error = validate_import_row(row)
            staged.append((i, row, "VALID" if ok else "INVALID", error))
            valid += 1 if ok else 0
            invalid += 0 if ok else 1
        try:
            self._repo.create_job(job_id=job_id, filename=command.filename,
                                  source_format=fmt, total=len(rows), valid=valid,
                                  invalid=invalid, created_by=command.user_id)
            for row_number, row, status, error in staged:
                self._repo.add_row(row_id=new_uuid(), job_id=job_id,
                                   row_number=row_number, payload=row,
                                   status=status, error=error)
            _emit(self._conn, ProductEvents.PRODUCT_IMPORT_BATCH_CREATED,
                  command.operation_id, job_id,
                  {"total": len(rows), "valid": valid, "invalid": invalid})
            self._conn.commit()
        except Exception:
            _rollback(self._conn)
            logger.exception("create import batch failed op=%s", command.operation_id)
            raise
        return ImportResult(True, job_id, "PRODUCT_IMPORT_BATCH_CREATED",
                            total=len(rows), valid=valid, invalid=invalid)


class ApproveImportBatchUseCase:
    name = "ApproveImportBatchUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductImportRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def execute(self, command: ImportBatchActionCommand) -> ImportResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.IMPORT_APPROVE)
        job = self._repo.get_job(command.job_id)
        if job is None:
            return ImportResult(False, None, "El batch no existe")
        if job["status"] != "PREVIEWED":
            return ImportResult(False, command.job_id,
                                f"El batch no está en vista previa ({job['status']})")
        # §39 segregación: quien creó el batch no puede aprobarlo.
        self._auth.ensure_segregation(
            actor_user_id=command.user_id or "", creator_user_id=job["created_by"],
            approval_permission=ProductPermissions.IMPORT_APPROVE)
        try:
            self._repo.set_status(command.job_id, "APPROVED",
                                  approved_by=command.user_id)
            _emit(self._conn, ProductEvents.PRODUCT_IMPORT_BATCH_APPROVED,
                  command.operation_id, command.job_id, {})
            self._conn.commit()
        except Exception:
            _rollback(self._conn)
            logger.exception("approve import batch failed op=%s", command.operation_id)
            raise
        return ImportResult(True, command.job_id, "PRODUCT_IMPORT_BATCH_APPROVED")


class ExecuteImportBatchUseCase:
    name = "ExecuteImportBatchUseCase"

    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProductImportRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()
        self._create = CreateProductMasterUseCase(connection, authorization)

    def execute(self, command: ImportBatchActionCommand) -> ImportResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.IMPORT_EXECUTE)
        job = self._repo.get_job(command.job_id)
        if job is None:
            return ImportResult(False, None, "El batch no existe")
        if job["status"] != "APPROVED":
            return ImportResult(False, command.job_id,
                                f"El batch debe estar aprobado ({job['status']})")
        created = int(job.get("created_rows") or 0)
        for row in self._repo.list_rows(command.job_id, status="VALID"):
            payload = row["payload"]
            code = str(payload.get("code") or "").strip()
            fields = {f: (payload.get(f) or None) for f in _MASTER_FIELDS
                      if f != "code"}
            cmd = CreateProductMasterCommand(
                operation_id=command.operation_id + ":" + str(row["row_number"]),
                code=code, auto_generate_code=not bool(code),
                user_id=command.user_id, **fields)
            try:
                result = self._create.execute(cmd)  # comitea el producto
            except Exception:  # noqa: BLE001 — una fila mala no detiene el batch
                logger.exception("import row create failed job=%s row=%s",
                                 command.job_id, row["row_number"])
                continue
            if result.success:
                self._repo.mark_created(row["id"], result.product_id)
                created += 1
        try:
            self._repo.set_created_count(command.job_id, created)
            self._repo.set_status(command.job_id, "EXECUTED")
            _emit(self._conn, ProductEvents.PRODUCT_IMPORT_BATCH_EXECUTED,
                  command.operation_id, command.job_id, {"created": created})
            self._conn.commit()
        except Exception:
            _rollback(self._conn)
            logger.exception("execute import batch failed op=%s", command.operation_id)
            raise
        return ImportResult(True, command.job_id, "PRODUCT_IMPORT_BATCH_EXECUTED",
                            created=created)


def _rollback(conn) -> None:
    rb = getattr(conn, "rollback", None)
    if rb is not None:
        rb()


def _emit(conn, event_name: str, operation_id: str, entity_id: str,
          extra: dict) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
               "operation_id": operation_id, "entity_id": entity_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, operation_id, entity_id,
         json.dumps(payload)))
