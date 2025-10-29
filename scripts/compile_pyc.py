#!/usr/bin/env python3
"""
Utility to clean and precompile .pyc bytecode for this project.

Notes:
- Python will auto-recompile .pyc on import if sources change, so running this is optional.
- Use this when you want to warm caches (e.g., in Docker images/CI) or ensure fresh bytecode after big refactors.

Examples:
  # Clean and compile default targets (app, scripts, tests)
  python scripts/compile_pyc.py --clean

  # Compile only the app package, force recompile
  python scripts/compile_pyc.py app --force

  # Clean only
  python scripts/compile_pyc.py --clean --no-compile

  # Customize optimize level and workers
  python scripts/compile_pyc.py --optimize 1 --workers 4
"""
from __future__ import annotations

import argparse
import compileall
import os
import shutil
import sys
from pathlib import Path

DEFAULT_TARGETS = [
    "app",
    "scripts",
    "tests",
]


def resolve_targets(paths: list[str] | None) -> list[Path]:
    if not paths:
        paths = DEFAULT_TARGETS
    root = Path(__file__).resolve().parents[1]
    resolved: list[Path] = []
    for p in paths:
        path = (root / p).resolve()
        if not path.exists():
            # Skip missing optional targets (e.g., tests may not exist in some envs)
            continue
        resolved.append(path)
    if not resolved:
        raise SystemExit("No valid targets to process.")
    return resolved


def clean_pyc(targets: list[Path]) -> int:
    removed_dirs = 0
    removed_files = 0
    for target in targets:
        for dirpath, dirnames, filenames in os.walk(target):
            # Remove __pycache__ dirs
            if "__pycache__" in dirnames:
                cache_dir = Path(dirpath) / "__pycache__"
                try:
                    shutil.rmtree(cache_dir)
                    removed_dirs += 1
                except Exception as e:
                    print(f"WARN: failed to remove {cache_dir}: {e}", file=sys.stderr)
            # Remove stray .pyc files (if any)
            for name in list(filenames):
                if name.endswith(".pyc"):
                    f = Path(dirpath) / name
                    try:
                        f.unlink(missing_ok=True)
                        removed_files += 1
                    except Exception as e:
                        print(f"WARN: failed to remove {f}: {e}", file=sys.stderr)
    print(f"Cleaned: {removed_dirs} __pycache__ dirs, {removed_files} .pyc files")
    return removed_dirs + removed_files


def compile_targets(targets: list[Path], *, force: bool, optimize: int, workers: int | None) -> bool:
    ok = True
    for target in targets:
        # compile_dir returns True if all compiled successfully, False otherwise
        # workers: None => single-threaded; >=2 uses multiprocessing
        w = None if not workers or workers < 2 else workers
        result = compileall.compile_dir(
            str(target),
            force=force,
            optimize=optimize,
            quiet=1,
            workers=w,
        )
        print(f"Compiled target: {target} -> {'OK' if result else 'FAIL'}")
        ok = ok and bool(result)
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean and precompile .pyc bytecode")
    parser.add_argument(
        "targets",
        nargs="*",
        help=f"Target directories (default: {', '.join(DEFAULT_TARGETS)})",
    )
    parser.add_argument("--clean", action="store_true", help="Remove existing __pycache__ and .pyc first")
    parser.add_argument("--no-compile", action="store_true", help="Only clean; skip compilation")
    parser.add_argument("--force", action="store_true", help="Force recompilation even if timestamps unchanged")
    parser.add_argument("--optimize", type=int, choices=[0, 1, 2], default=0, help="Optimize level for compilation")
    parser.add_argument("--workers", type=int, default=0, help="Number of worker processes (>=2 enables parallel)")

    args = parser.parse_args(argv)

    targets = resolve_targets(args.targets)

    if args.clean:
        clean_pyc(targets)

    if args.no_compile:
        return 0

    success = compile_targets(targets, force=args.force or args.clean, optimize=args.optimize, workers=args.workers)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
