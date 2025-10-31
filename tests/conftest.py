"""Pytest configuration and helpers.

Ensures the project root is on sys.path for `import app` to work when running tests.
"""

import os
import sys


def _add_project_root_to_syspath() -> None:
    # tests/ directory -> project root
    this_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(this_dir, os.pardir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


_add_project_root_to_syspath()
