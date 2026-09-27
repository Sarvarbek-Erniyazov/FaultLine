"""Course Lesson 11 tests: put the repository root on the import path.

``pytest`` runs in importlib mode (pyproject), which does not add the root directory to
``sys.path``, and the Lesson 11 packages (``inference``, ``evaluation``, ``deployment``) sit at
the root rather than under ``src/``. Only this folder's tests need them.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
