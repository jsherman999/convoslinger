"""Render the manifest and parsed conversations into the static site."""

import html
from datetime import date

from . import markdown as md
from .manifest import display_order
from .paths import CONVOS_DIR, INDEX

ROLE_LABEL = {
    "user": "You",
    "assistant": "Claude",
    "system": "System",
    "thinking": "Thinking",
    "note": "",
}


def _e(text) -> str:
    return html.escape(str(text or ""), quote=True)


def _head(title: str, description: str, css: str, extra: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<meta name="description" content="{_e(description)}">
<meta name="color-scheme" content="dark">
<meta property="og:title" content="{_e(title)}">
<meta property="og:description" content="{_e(description)}">
<meta property="og:type" content="article">
<link rel="stylesheet" href="{css}">
{extra}</head>"""


def render_turn(item: dict) -> str:
    role = item.get("role", "note")
    if item.get("kind") == "tool":
        label = _e(item.get("label") or "tool")
        return (
            f'<details class="turn tool"><summary><span class="who">tool</span> {label}</summary>'
            f'<div class="body">{md.render(item["text"])}</div></details>'
        )
    label = ROLE_LABEL.get(role, role.title())
    who = f'<div class="who">{_e(label)}</div>' if label else ""
    return f'<article class="turn {_e(role)}">{who}<div class="body">{md.render(item["text"])}</div></article>'


def render_convo_page(entry: dict, turns: list, site: dict) -> str:
    site_title = site.get("title") or "saved convos"
    tags = "".join(f'<span class="tag">{_e(t)}</span>' for t in entry.get("tags", []))
    spoken = sum(1 for t in turns if t.get("kind") == "md" and t.get("role") != "note")
    count = f'<span class="count">{spoken} messages</span>' if spoken > 1 else ""
    synopsis = (
        f'<p class="synopsis">{_e(entry["synopsis"])}</p>' if entry.get("synopsis") else ""
    )
    body = "".join(render_turn(t) for t in turns) or '<p class="empty">This conversation is empty.</p>'
    return f"""{_head(f"{entry['title']} · {site_title}", entry.get("synopsis", ""), "../assets/style.css")}
<body class="convo">
<div class="wrap">
<header class="page-head">
<a class="back" href="../">&larr; {_e(site_title)}</a>
<h1>{_e(entry['title'])}</h1>
<p class="meta"><time datetime="{_e(entry['date'])}">{_e(entry['date'])}</time>{count}{tags}</p>
{synopsis}
</header>
<main class="thread">
{body}
</main>
<footer class="page-foot"><a href="../">&larr; all conversations</a></footer>
</div>
</body>
</html>
"""


def render_index(manifest: dict) -> str:
    site = manifest["site"]
    items = display_order(manifest)
    title = site.get("title") or "saved convos"
    tagline = f'<p class="tagline">{_e(site["tagline"])}</p>' if site.get("tagline") else ""

    rows = []
    for entry in items:
        haystack = " ".join(
            [entry["title"], entry.get("synopsis", ""), " ".join(entry.get("tags", []))]
        ).lower()
        tags = "".join(
            f'<button class="tag" type="button" data-tag="{_e(t)}">{_e(t)}</button>'
            for t in entry.get("tags", [])
        )
        pin = '<span class="pin" title="pinned">&#9679;</span>' if entry.get("pinned") else ""
        synopsis = f'<p class="synopsis">{_e(entry["synopsis"])}</p>' if entry.get("synopsis") else ""
        rows.append(
            f'<li class="item" data-search="{_e(haystack)}">'
            f'<a class="item-link" href="{_e(entry["path"])}">'
            f'<time datetime="{_e(entry["date"])}">{_e(entry["date"])}</time>'
            f'<h2>{pin}{_e(entry["title"])}</h2>{synopsis}</a>'
            f'<div class="tags">{tags}</div></li>'
        )

    listing = (
        f'<ol class="list">{"".join(rows)}</ol>'
        if rows
        else '<p class="empty">Nothing published yet.</p>'
    )
    search = (
        '<div class="filter"><input id="q" type="search" placeholder="filter" '
        'autocomplete="off" spellcheck="false" aria-label="filter conversations">'
        '<span id="hits"></span></div>'
        if len(rows) > 4
        else ""
    )
    footer = f'<p>{md.inline(site["footer"])}</p>' if site.get("footer") else ""

    return f"""{_head(title, site.get("tagline", ""), "assets/style.css")}
<body class="index">
<div class="wrap">
<header class="site-head">
<h1>{_e(title)}</h1>
{tagline}
</header>
{search}
<main>
{listing}
</main>
<footer class="site-foot">{footer}</footer>
</div>
<script>
(function () {{
  var q = document.getElementById('q');
  if (!q) return;
  var items = Array.prototype.slice.call(document.querySelectorAll('.item'));
  var hits = document.getElementById('hits');
  function apply() {{
    var term = q.value.trim().toLowerCase();
    var shown = 0;
    items.forEach(function (li) {{
      var match = !term || li.dataset.search.indexOf(term) !== -1;
      li.hidden = !match;
      if (match) shown++;
    }});
    hits.textContent = term ? shown + ' of ' + items.length : '';
  }}
  q.addEventListener('input', apply);
  document.addEventListener('click', function (e) {{
    var tag = e.target.closest('.tag');
    if (!tag) return;
    q.value = q.value.trim() === tag.dataset.tag ? '' : tag.dataset.tag;
    apply();
    q.focus();
  }});
}})();
</script>
</body>
</html>
"""


def write_convo(entry: dict, turns: list, site: dict):
    CONVOS_DIR.mkdir(parents=True, exist_ok=True)
    target = CONVOS_DIR / f"{entry['id']}.html"
    target.write_text(render_convo_page(entry, turns, site), encoding="utf-8")
    return target


def write_index(manifest: dict):
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(render_index(manifest), encoding="utf-8")
    return INDEX


def today() -> str:
    return date.today().isoformat()
