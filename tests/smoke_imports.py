#!/usr/bin/env python3

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Top-level packages that make up the application after the gateway/agent refactor.
PACKAGES = (
    "agent",
    "config",
    "gateway",
    "shared_types",
    "tools",
    "web",
)


def module_name(path: Path) -> str:
    relative = path.relative_to(ROOT)
    if relative.name == "__init__.py":
        return ".".join(relative.parts[:-1])
    return ".".join(relative.with_suffix("").parts)


def iter_modules() -> list[str]:
    modules: list[str] = []
    for package in PACKAGES:
        package_dir = ROOT / package
        if not package_dir.is_dir():
            continue
        for path in sorted(package_dir.rglob("*.py")):
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
