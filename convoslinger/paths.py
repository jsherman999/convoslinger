"""Well-known locations inside the repository."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
CONVOS_DIR = DOCS / "convos"
MANIFEST = DOCS / "convos.json"
INDEX = DOCS / "index.html"
INBOX = ROOT / "inbox"
STATIC = Path(__file__).resolve().parent / "static"
