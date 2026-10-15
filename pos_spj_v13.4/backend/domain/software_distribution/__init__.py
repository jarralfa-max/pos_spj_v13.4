"""Software distribution bounded context — releases, installed version,
install profiles and the policies that decide whether an update may be
offered, downloaded or installed.

Pure domain: no I/O, no Qt, no SQL. The updater infrastructure
(`backend/infrastructure/updater/`) and the application use cases
(`backend/application/software_updates/`) depend on this package, never the
other way around.
"""
