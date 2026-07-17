"""Application layer for the suppliers bounded context.

Use cases (mutations) and query services (reads) that orchestrate the domain and
the repositories. Every mutation validates permissions + state, runs inside a
UnitOfWork, records audit and enqueues events post-commit.
"""
