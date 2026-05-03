
import os
import ast

PROJECT_ROOT = "."

def get_defined_names(filepath):
    """Devuelve clases y funciones definidas en un archivo"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return set()

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
    return names


def scan_project():
    errors = []

    for root, dirs, files in os.walk(PROJECT_ROOT):
        for file in files:
            if not file.endswith(".py"):
                continue

            path = os.path.join(root, file)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except Exception as e:
                errors.append((path, "SyntaxError", str(e)))
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):

                    module = node.module
                    if not module:
                        continue

                    module_path = module.replace(".", "/") + ".py"

                    if not os.path.exists(module_path):
                        continue

                    defined = get_defined_names(module_path)

                    for alias in node.names:
                        name = alias.name

                        if name not in defined:
                            errors.append((path, module, name))

    return errors


def main():
    errors = scan_project()

    if not errors:
        print("✅ No se encontraron imports rotos")
        return

    print("⚠ Imports potencialmente rotos:\n")

    for e in errors:
        print(e)


if __name__ == "__main__":
    main()