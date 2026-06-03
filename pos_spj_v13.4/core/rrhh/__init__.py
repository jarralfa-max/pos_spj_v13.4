"""RRHH bounded context.

Phase 1 keeps these classes additive: current PyQt screens and services continue
using their legacy paths until the refactor wiring phase opts in.
"""

__all__ = ["domain", "application", "infrastructure", "events"]
