"""
Root conftest for the backend — adds the monorepo root to sys.path.

This runs before any test collection, making `packages.*` importable
without needing the full FastAPI app stack.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
