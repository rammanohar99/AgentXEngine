"""
Root conftest for the backend — adds apps/backend/ to sys.path.

This runs before any test collection, making `packages.*` importable
without needing the full FastAPI app stack.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
