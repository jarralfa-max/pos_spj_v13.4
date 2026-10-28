"""PreToolUse guard for SPJ ERP (SDLC playbook: hard guards).

Blocks, before they run:
- edits/writes to live databases, secrets, signing keys and logs;
- destructive or release-publishing shell commands.

Claude Code passes the tool call as JSON on stdin. Exit code 2 blocks the
call and the stderr message is shown to Claude so it can change course.
Standard library only, works on Windows and Linux.
"""
from __future__ import annotations

import json
import re
import sys

PROTECTED_FILE = re.compile(
    r"""(
        \.(db|sqlite|sqlite3|db-wal|db-shm)$      # live databases
      | (^|[\\/])\.env(\.[^\\/]*)?$              # env files
      | \.(pem|key|pfx|p12)$                     # keys / certificates
      | (^|[\\/])logs[\\/]                       # runtime logs
      | (^|[\\/])secrets?[\\/]
    )""",
    re.IGNORECASE | re.VERBOSE,
)

BLOCKED_COMMANDS = [
    (r"\bgit\s+push\b.*(--force\b|-f\b|--force-with-lease)", "force-push"),
    (r"\bgit\s+push\b[^;&|]*[\s:+](main|master)(\s|$)", "push a main/master"),
    (r"\bgit\s+push\b.*--tags|\bgit\s+tag\s+v\d", "crear/publicar tags de release"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\s+-[a-z]*f", "git clean -f"),
    (r"\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)", "descartar todos los cambios"),
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r", "rm -rf"),
    (r"\b(Remove-Item|del|rmdir|rd)\b.*(-Recurse|/s)", "borrado recursivo"),
    (r"\bgh\s+(release|workflow\s+run|pr\s+merge)\b", "publicar release / disparar workflow / merge"),
    (r"(\b(rm|del|Remove-Item)\b|>\s*)[^|;&]*\.(db|sqlite|sqlite3)\b", "borrar o sobrescribir una base de datos"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "DROP TABLE/DATABASE"),
]


def block(reason: str) -> None:
    print(
        f"Bloqueado por .claude/hooks/guard.py: {reason}. "
        "Si de verdad es necesario, explícale al usuario por qué y pídele que lo haga él.",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    tool = data.get("tool_name", "")
    params = data.get("tool_input", {}) or {}

    if tool in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        path = str(params.get("file_path") or params.get("notebook_path") or "")
        if PROTECTED_FILE.search(path):
            block(f"edición de archivo protegido ({path})")

    elif tool == "Bash":
        command = str(params.get("command", ""))
        for pattern, label in BLOCKED_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                block(label)


if __name__ == "__main__":
    main()
