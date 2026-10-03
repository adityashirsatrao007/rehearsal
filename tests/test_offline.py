"""The offline promise is the product, so it is tested rather than left as prose.

"One download, then practising is free" and "there is no outbound call to make"
are the two claims the whole project rests on. A single absolute URL pointing
anywhere that is not loopback would quietly break both, and nobody would notice
until a judge tried it with the Wi-Fi off. These tests notice immediately.
"""
from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

import pytest

from app import llm

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "app").glob("*.py")) + sorted(
    p for p in (ROOT / "static").glob("*") if p.is_file()
)

# XML namespace identifiers look like URLs but are never fetched.
_XML_NS = {"www.w3.org"}
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}

_URL = re.compile(r"https?://([A-Za-z0-9._-]+)")
_FETCH = re.compile(r"""\bfetch\(\s*["'`]([^"'`]*)""")
_REMOTE_ASSET = re.compile(
    r"""<(?:script|link|img|iframe|source|video)\b[^>]*?(?:src|href)\s*=\s*["'](https?://[^"']+)""",
    re.IGNORECASE,
)


def test_ollama_host_is_loopback_by_default() -> None:
    """The one machine this app talks to is this machine."""
    if "OLLAMA_HOST" in os.environ:
        pytest.skip("OLLAMA_HOST is deliberately overridden in this environment")
    assert urllib.parse.urlparse(llm.OLLAMA_HOST).hostname in _LOOPBACK


def test_no_absolute_url_in_the_source_leaves_the_machine() -> None:
    leaked = [
        f"{path.name}: {match.group(0)}"
        for path in SOURCES
        for match in _URL.finditer(path.read_text(encoding="utf-8"))
        if match.group(1) not in _LOOPBACK and match.group(1) not in _XML_NS
    ]
    assert not leaked, f"non-loopback URL found in source: {leaked}"


def test_every_frontend_fetch_is_same_origin() -> None:
    """The browser only ever calls back into this server."""
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    targets = _FETCH.findall(js)
    assert targets, "expected the frontend to make some fetch calls"
    cross = [t for t in targets if t.startswith(("http://", "https://", "//"))]
    assert not cross, f"cross-origin fetch found: {cross}"


def test_index_loads_no_remote_assets() -> None:
    """No CDN font, no analytics script, no tracker hiding in a <link>."""
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    remote = [
        url
        for url in _REMOTE_ASSET.findall(html)
        if urllib.parse.urlparse(url).hostname not in _XML_NS
    ]
    assert not remote, f"remote asset referenced by index.html: {remote}"


def test_transcript_is_a_local_sqlite_file_not_a_service() -> None:
    """The transcript is a file. There is no sync endpoint to opt out of."""
    from app import store

    db_path = Path(store.DB_PATH)
    assert db_path.suffix == ".db"
    assert not str(db_path).startswith(("http://", "https://", "sqlite://"))
    assert db_path.is_absolute()


def test_suite_runs_against_a_throwaway_database() -> None:
    """Importing the test suite must never open a real transcript."""
    from app import store

    assert "rehearsal-test-" in str(store.DB_PATH), (
        f"tests are pointed at {store.DB_PATH}, not a throwaway file"
    )


def test_a_real_transcript_cannot_be_pushed_by_accident() -> None:
    """`data/` is gitignored — a friend's practice history stays off GitHub."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^data/\s*$", gitignore, re.MULTILINE), "data/ is not gitignored"
    assert re.search(r"^\*\.db\s*$", gitignore, re.MULTILINE), "*.db is not gitignored"
