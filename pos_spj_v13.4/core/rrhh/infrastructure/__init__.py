"""Infrastructure adapters for RRHH."""

from .sqlite_repositories import (
    SQLiteAttendanceRepository,
    SQLiteEmployeeIdentityRepository,
    SQLiteEmployeeRepository,
    SQLiteLeaveRepository,
    SQLitePayrollRepository,
    SQLiteShiftRepository,
)

__all__ = [
    "SQLiteAttendanceRepository",
    "SQLiteEmployeeIdentityRepository",
    "SQLiteEmployeeRepository",
    "SQLiteLeaveRepository",
    "SQLitePayrollRepository",
    "SQLiteShiftRepository",
]
