"""Shared pytest setup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the repo root importable so `import handler` works.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Tests should not see any operator credentials.
for key in ("RUNPOD_API_KEY", "RUNPOD_ENDPOINT_ID", "MINERU_TEMPLATE_ID"):
    os.environ.pop(key, None)
