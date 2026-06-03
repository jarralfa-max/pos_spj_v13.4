"""Infrastructure adapters for RRHH."""

from .sqlite_repositories import (
    SQLiteAttendanceRepository,
    SQLiteEmployeeRepository,
    SQLiteLeaveRepository,
    SQLitePayrollRepository,
    SQLiteShiftRepository,
)

__all__ = [
    "SQLiteAttendanceRepository",
    "SQLiteEmployeeRepository",
    "SQLiteLeaveRepository",
    "SQLitePayrollRepository",
    "SQLiteShiftRepository",
]
