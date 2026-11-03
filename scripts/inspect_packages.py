#!/usr/bin/env python3
"""Print a source-level inventory for one or more installed distributions.

Run this with each benchmark environment's Python executable.  The script is
read-only: it reports metadata, import paths, modules, Python definitions, and
console entry points without importing every submodule or editing site-packages.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.metadata as metadata
import inspect
import json
from pathlib import Path


def definitions(path: Path) -> list[dict[str, object]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    return [
        {"kind": type(node).__name__, "name": node.name, "line": node.lineno}
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def inspect_distribution(dist_name: str) -> dict[str, object]:
    dist = metadata.distribution(dist_name)
    import_name = dist_name.replace("-", "_")
    module = importlib.import_module(import_name)
    package_dir = Path(inspect.getfile(module)).resolve().parent
    py_files = sorted(package_dir.glob("*.py"))
    return {
        "distribution": dist.metadata["Name"],
        "version": dist.version,
        "python_requires": dist.metadata.get("Requires-Python"),
        "requirements": list(dist.requires or []),
        "metadata_license": dist.metadata.get("License"),
        "import_name": import_name,
        "import_file": str(Path(inspect.getfile(module)).resolve()),
        "package_files": [
            {
                "path": str(path),
                "lines": len(path.read_text(encoding="utf-8", errors="replace").splitlines()),
                "definitions": definitions(path),
            }
            for path in py_files
        ],
        "console_scripts": [
            {"name": ep.name, "value": ep.value}
            for ep in dist.entry_points
            if ep.group == "console_scripts"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="+", help="Distribution names, e.g. swing-analyzer")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    result = {name: inspect_distribution(name) for name in args.packages}
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
