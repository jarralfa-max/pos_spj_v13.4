"""PostToolUse: after Claude edits a .py file, make sure it still parses.

Replaces the previous inline hook, which read a CLAUDE_TOOL_INPUT_FILE_PATH
environment variable that Claude Code does not set (the tool call arrives as
JSON on stdin), so it never checked anything. Reads UTF-8 explicitly so it
also works with Windows' default code page.
"""
from __future__ import annotations

import ast
import json
import os
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    path = str((data.get("tool_input") or {}).get("file_path") or "")
    if not path.endswith(".py") or not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8-sig") as fh:
            ast.parse(fh.read(), filename=path)
    except SyntaxError as exc:
        print(f"SYNTAX ERROR en {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    except UnicodeDecodeError as exc:
        print(f"{path} no es UTF-8 válido: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
