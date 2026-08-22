"""Read/write docs/convos.json — the single file that decides what the site shows."""

import json
import re
import unicodedata
from datetime import date, datetime, timezone

from .paths import MANIFEST

VERSION = 1

DEFAULT_SITE = {
    "title": "saved convos",
    "tagline": "conversations worth keeping",
    "footer": "",
    "sort": "date",  # "date" (newest first) or "manual" (manifest order)
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty() -> dict:
    return {"version": VERSION, "site": dict(DEFAULT_SITE), "convos": []}


def load() -> dict:
    if not MANIFEST.exists():
        return empty()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    site = dict(DEFAULT_SITE)
    site.update(data.get("site") or {})
    return {
        "version": data.get("version", VERSION),
        "site": site,
        "convos": [normalize(c) for c in data.get("convos") or []],
    }


def save(manifest: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": VERSION,
        "site": manifest.get("site") or dict(DEFAULT_SITE),
        "convos": [normalize(c) for c in manifest.get("convos") or []],
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


KNOWN = {
    "id", "title", "synopsis", "date", "tags", "path", "visible",
    "pinned", "source", "added", "format", "source_file", "raw_html",
    "include_thinking",
}


def normalize(entry: dict) -> dict:
    out = {
        "id": entry.get("id") or slugify(entry.get("title", "untitled")),
        "title": (entry.get("title") or "Untitled").strip(),
        "synopsis": (entry.get("synopsis") or "").strip(),
        "date": entry.get("date") or date.today().isoformat(),
        "tags": [t.strip() for t in (entry.get("tags") or []) if t.strip()],
        "path": entry.get("path") or f"convos/{entry.get('id', 'untitled')}.html",
        "visible": bool(entry.get("visible", True)),
        "pinned": bool(entry.get("pinned", False)),
        "source": entry.get("source") or "unknown",
        "added": entry.get("added") or _now(),
        "format": entry.get("format") or "markdown",
        "source_file": entry.get("source_file") or f"sources/{entry.get('id', 'untitled')}.md",
        "raw_html": bool(entry.get("raw_html", False)),
        "include_thinking": bool(entry.get("include_thinking", False)),
    }
    # Anything hand-added to the JSON survives a round-trip untouched.
    out.update({k: v for k, v in entry.items() if k not in KNOWN})
    return out


def slugify(text: str, maxlen: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)[:maxlen].strip("-")
    return text or "convo"


def make_id(manifest: dict, title: str, when: str) -> str:
    base = f"{when}-{slugify(title)}"
    taken = {c["id"] for c in manifest["convos"]}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def find(manifest: dict, convo_id: str):
    for entry in manifest["convos"]:
        if entry["id"] == convo_id:
            return entry
    return None


def display_order(manifest: dict, include_hidden: bool = False) -> list:
    """Pinned first, then by the site's chosen sort."""
    items = [c for c in manifest["convos"] if include_hidden or c["visible"]]
    if manifest["site"].get("sort", "date") == "date":
        items.sort(key=lambda c: (c["date"], c["added"]), reverse=True)
    items.sort(key=lambda c: not c["pinned"])
    return items
