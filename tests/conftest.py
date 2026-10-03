"""Point tests at a throwaway database before the app modules are imported."""

import os
import tempfile
from pathlib import Path

_tmpdir = tempfile.mkdtemp(prefix="rehearsal-test-")
os.environ["REHEARSAL_DB"] = str(Path(_tmpdir) / "test.db")
os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import pytest  # noqa: E402

from app import store  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts from an empty database."""
    store.reset_db()
    yield
