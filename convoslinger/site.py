"""Import conversations and (re)generate everything under docs/.

Truth lives in two places and nowhere else:
  * sources/<id>.(md|jsonl|html) — the raw export, exactly as you saved it
  * docs/convos.json             — what the site should show

Everything under docs/convos/ and docs/index.html is generated from those two,
so a rebuild is always safe and nothing is edited by hand.
"""

import shutil
from datetime import date

from . import manifest as mf
from . import parse, render, scrub
from .paths import CONTENT, CONVOS_DIR, DOCS, INBOX, SOURCES

EXT = {"markdown": ".md", "jsonl": ".jsonl", "html": ".html"}

BACK_BAR = (
    '<div style="font:12px ui-monospace,Menlo,monospace;padding:10px 16px;'
    'background:#0c0c0d;border-bottom:1px solid #232326">'
    '<a href="../" style="color:#8a8781;text-decoration:none">&larr; all conversations</a></div>'
)


def source_path(entry: dict):
    return CONTENT / entry["source_file"]


def import_text(
    text: str,
    filename: str = "",
    title: str | None = None,
    when: str | None = None,
    tags: list | None = None,
    synopsis: str | None = None,
    scrub_secrets: bool = True,
    visible: bool = True,
    include_thinking: bool = False,
    raw_html: bool = False,
    prompt: str = "",
) -> tuple[dict, list]:
    """Add one conversation. Returns (entry, possible-secret findings)."""
    findings = scrub.scan(text)
    if scrub_secrets:
        text, _ = scrub.scrub(text)

    fmt = parse.detect_format(text, filename)
    turns = [] if fmt == "html" else parse.parse(text, filename, include_thinking)
    prompt = (prompt or "").strip()
    if prompt and turns:
        # Title and synopsis should come from the question, not from the answer.
        turns = [parse.turn("user", prompt)] + [
            parse.turn("assistant", t["text"], t["kind"], t["label"]) if t["role"] == "note" else t
            for t in turns
        ]

    manifest = mf.load()
    when = when or date.today().isoformat()
    title = (title or "").strip() or (
        parse.auto_title(turns) if turns else (filename or "Saved conversation")
    )
    convo_id = mf.make_id(manifest, title, when)

    entry = mf.normalize(
        {
            "id": convo_id,
            "title": title,
            "synopsis": synopsis
            if synopsis is not None
            else (parse.auto_synopsis(turns, skip=title) if turns else ""),
            "date": when,
            "tags": tags or [],
            "path": f"convos/{convo_id}.html",
            "visible": visible,
            "source": {"jsonl": "claude-code", "html": "html", "markdown": "claude-app"}[fmt],
            "prompt": prompt,
        }
    )
    entry["format"] = fmt
    entry["raw_html"] = bool(raw_html and fmt == "html")
    entry["source_file"] = f"sources/{convo_id}{EXT[fmt]}"

    SOURCES.mkdir(parents=True, exist_ok=True)
    source_path(entry).write_text(text, encoding="utf-8")

    manifest["convos"].insert(0, entry)
    mf.save(manifest)
    build(manifest)
    return entry, findings


def turns_for(entry: dict, text: str | None = None) -> list:
    """Parse an entry's source into turns, prepending its question if it has one.

    An export that carries only Claude's reply parses to a single unattributed
    block; given a question it becomes a proper two-turn exchange.
    """
    src = source_path(entry)
    if text is None:
        text = src.read_text(encoding="utf-8", errors="replace")
    turns = parse.parse(text, src.name, entry.get("include_thinking", False))
    question = (entry.get("prompt") or "").strip()
    if not question:
        return turns
    body = [
        parse.turn("assistant", t["text"], t["kind"], t["label"]) if t["role"] == "note" else t
        for t in turns
    ]
    return [parse.turn("user", question)] + body


def render_entry(entry: dict, site: dict) -> None:
    """Write docs/convos/<id>.html from the entry's stored source."""
    src = source_path(entry)
    if not src.exists():
        raise FileNotFoundError(f"missing source for {entry['id']}: {entry['source_file']}")
    CONVOS_DIR.mkdir(parents=True, exist_ok=True)
    target = CONVOS_DIR / f"{entry['id']}.html"

    if entry.get("format") == "html":
        page = src.read_text(encoding="utf-8", errors="replace")
        if not entry.get("raw_html"):
            lower = page.lower()
            at = lower.find("<body")
            if at != -1:
                at = page.find(">", at) + 1
                page = page[:at] + BACK_BAR + page[at:]
            else:
                page = BACK_BAR + page
        target.write_text(page, encoding="utf-8")
        return

    target.write_text(
        render.render_convo_page(entry, turns_for(entry), site), encoding="utf-8"
    )


def build(manifest: dict | None = None) -> dict:
    """Regenerate docs/ from the manifest. Hidden conversations lose their page."""
    manifest = manifest or mf.load()
    CONVOS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").touch()

    keep = set()
    problems = []
    for entry in manifest["convos"]:
        page = CONVOS_DIR / f"{entry['id']}.html"
        if entry["visible"]:
            try:
                render_entry(entry, manifest["site"])
                keep.add(page.name)
            except FileNotFoundError as exc:
                problems.append(str(exc))
        elif page.exists():
            page.unlink()  # unlisted *and* unreachable, not just hidden from the list

    for stale in CONVOS_DIR.glob("*.html"):
        if stale.name not in keep:
            stale.unlink()

    render.write_index(manifest)
    return {"built": len(keep), "problems": problems}


def delete(convo_id: str, drop_source: bool = True) -> bool:
    manifest = mf.load()
    entry = mf.find(manifest, convo_id)
    if not entry:
        return False
    manifest["convos"] = [c for c in manifest["convos"] if c["id"] != convo_id]
    if drop_source:
        src = source_path(entry)
        if src.exists():
            src.unlink()
    page = CONVOS_DIR / f"{convo_id}.html"
    if page.exists():
        page.unlink()
    mf.save(manifest)
    build(manifest)
    return True


def inbox_items() -> list:
    """Files dropped into inbox/ (e.g. by the phone shortcut) awaiting import."""
    if not INBOX.exists():
        return []
    out = []
    for path in sorted(INBOX.iterdir()):
        if path.name.startswith(".") or path.suffix.lower() not in (".md", ".txt", ".jsonl", ".html", ".htm"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        turns = parse.parse(text, path.name) if path.suffix.lower() not in (".html", ".htm") else []
        out.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "suggested_title": parse.auto_title(turns, path.stem) if turns else path.stem,
                "suggested_synopsis": parse.auto_synopsis(turns) if turns else "",
                "secrets": len(scrub.scan(text)),
            }
        )
    return out


def import_inbox_file(name: str, archive: bool = True, **kwargs) -> tuple[dict, list]:
    path = INBOX / name
    if not path.exists() or path.parent != INBOX:
        raise FileNotFoundError(name)
    entry, findings = import_text(path.read_text(encoding="utf-8", errors="replace"), path.name, **kwargs)
    if archive:
        done = INBOX / "imported"
        done.mkdir(exist_ok=True)
        shutil.move(str(path), str(done / path.name))
    return entry, findings
