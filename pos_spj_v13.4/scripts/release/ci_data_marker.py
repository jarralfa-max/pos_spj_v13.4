"""CI helper: prove that repair/upgrade/uninstall keep the station's data.

    python ci_data_marker.py write <database>   → adds a marker row
    python ci_data_marker.py check <database>   → exit 0 only if the row is there

Uses the runner's Python only to INSPECT the database file; the installed
application itself runs without Python on PATH.
"""
from __future__ import annotations

import sqlite3
import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in {"write", "check"}:
        print(__doc__)
        return 2
    command, database = argv
    connection = sqlite3.connect(database)
    try:
        if command == "write":
            connection.execute("CREATE TABLE IF NOT EXISTS ci_marker (v TEXT)")
            connection.execute("INSERT INTO ci_marker VALUES ('keep')")
            connection.commit()
            print("marker escrito")
            return 0
        row = connection.execute("SELECT v FROM ci_marker").fetchone()
    except sqlite3.Error as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        connection.close()
    ok = bool(row and row[0] == "keep")
    print("marker presente" if ok else "marker AUSENTE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
