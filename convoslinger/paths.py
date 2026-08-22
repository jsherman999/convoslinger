"""Well-known locations.

The app's code and the conversations it publishes live on different branches,
so they live in different directories too. `content/` is normally a git
worktree of the site branch:

    convoslinger/        the app, on its own branch
      content/           worktree of the `site` branch — docs/, sources/, inbox/

Set CONVOSLINGER_CONTENT to put the content anywhere else. If neither is
present everything falls back to the repository root, which is the old
single-branch layout — existing checkouts keep working untouched.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the app checkout
STATIC = Path(__file__).resolve().parent / "static"


def content_root() -> Path:
    override = os.environ.get("CONVOSLINGER_CONTENT")
    if override:
        return Path(override).expanduser().resolve()
    worktree = ROOT / "content"
    if (worktree / "docs").is_dir() or (worktree / ".git").exists():
        return worktree
    return ROOT


CONTENT = content_root()
DOCS = CONTENT / "docs"
ASSETS = DOCS / "assets"
CONVOS_DIR = DOCS / "convos"
MANIFEST = DOCS / "convos.json"
INDEX = DOCS / "index.html"
SOURCES = CONTENT / "sources"
INBOX = CONTENT / "inbox"
