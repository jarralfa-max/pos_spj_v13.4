"""Exclusive transaction for the one-time installation provisioning operation."""
from backend.infrastructure.db.unit_of_work import UnitOfWork


class ProvisioningUnitOfWork(UnitOfWork):
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        if self.connection.in_transaction:
            raise RuntimeError("Provisioning requires a connection with no pending transaction.")
        # Serialize concurrent first-run attempts before reading installation state.
        self.connection.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            self.rollback()
        else:
            try:
                self.commit()
            except Exception:
                self.rollback()
                raise
        return False

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()
