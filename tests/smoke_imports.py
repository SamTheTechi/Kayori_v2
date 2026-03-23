#!/usr/bin/env python3

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"


def module_name(path: Path) -> str:
    relative = path.relative_to(SRC_DIR)
    if relative.name == "__init__.py":
        parts = ("src",) + relative.parts[:-1]
        return ".".join(parts)
    parts = ("src",) + relative.with_suffix("").parts
    return ".".join(parts)


def iter_modules() -> list[str]:
    modules: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if path.name == "__main__.py":
            continue
        name = module_name(path)
        if name:
            modules.append(name)
    return modules


def main() -> int:
    sys.path.insert(0, str(ROOT))

    failures: list[tuple[str, str]] = []
    for name in iter_modules():
        try:
            importlib.import_module(name)
        except Exception:
            failures.append((name, traceback.format_exc()))

    if failures:
        print("Import smoke test failed:")
        for name, error in failures:
            print(f"\n[{name}]")
            print(error.rstrip())
        return 1

    print("Import smoke test passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
