"""A small, dependency-free Markdown subset renderer.

Covers what actually shows up in Claude transcripts: fenced code, headings,
lists, blockquotes, pipe tables, rules, links, images, and the usual inline
emphasis. Anything it does not recognise is emitted as an escaped paragraph,
so unknown syntax degrades to readable text rather than breaking the page.
"""

import html
import re

SAFE_SCHEME = re.compile(r"^(https?:|mailto:|#|/|\./|\.\./|[^:]*$)", re.I)

_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+-]*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_UL = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL = re.compile(r"^(\s*)(\d{1,9})[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def safe_url(url: str) -> str:
    url = (url or "").strip()
    if not SAFE_SCHEME.match(url):
        return "#"
    return html.escape(url, quote=True)


def inline(text: str) -> str:
    """Render inline markdown. Escapes everything it does not turn into a tag."""
    slots: list[str] = []

    def stash(rendered: str) -> str:
        slots.append(rendered)
        return f"\x00{len(slots) - 1}\x00"

    # Code spans first: their contents must not be touched by anything else.
    def code_span(match: re.Match) -> str:
        return stash(f"<code>{html.escape(match.group(2))}</code>")

    text = re.sub(r"(?<!`)(`+)([^`]|[^`].*?[^`])\1(?!`)", code_span, text, flags=re.S)

    def image(match: re.Match) -> str:
        alt = html.escape(match.group(1), quote=True)
        return stash(f'<img src="{safe_url(match.group(2))}" alt="{alt}" loading="lazy">')

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)

    def link(match: re.Match) -> str:
        return stash(
            f'<a href="{safe_url(match.group(2))}" rel="noopener noreferrer">'
            f"{inline(match.group(1))}</a>"
        )

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)

    def autolink(match: re.Match) -> str:
        url = match.group(0).rstrip(".,;:!?)")
        trail = match.group(0)[len(url):]
        return stash(f'<a href="{safe_url(url)}" rel="noopener noreferrer">{html.escape(url)}</a>') + trail

    text = re.sub(r"https?://[^\s<>\x00]+", autolink, text)

    text = html.escape(text)
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text, flags=re.S)
    text = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<strong>\1</strong>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?=\S)([^_]+?)(?<=\S)_(?![\w_])", r"<em>\1</em>", text)
    text = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<del>\1</del>", text, flags=re.S)

    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _render_table(rows: list[str]) -> str:
    def cells(row: str) -> list[str]:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]

    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    out = ["<div class='table-wrap'><table><thead><tr>"]
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render(text: str) -> str:
    """Render a markdown document to HTML."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return _blocks(lines)


def _blocks(lines: list[str]) -> str:
    out: list[str] = []
    para: list[str] = []
    i = 0

    def flush() -> None:
        if para:
            out.append("<p>" + inline("\n".join(para)).replace("\n", "<br>") + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]

        fence = _FENCE.match(line)
        if fence:
            flush()
            marker, lang = fence.group(2)[0], fence.group(3)
            i += 1
            body: list[str] = []
            while i < len(lines) and not re.match(rf"^\s*{marker}{{3,}}\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
            label = f'<span class="code-lang">{html.escape(lang)}</span>' if lang else ""
            out.append(
                f'<div class="code-block">{label}<pre><code{cls}>'
                f'{html.escape(chr(10).join(body))}</code></pre></div>'
            )
            continue

        if not line.strip():
            flush()
            i += 1
            continue

        if _HR.match(line):
            flush()
            out.append("<hr>")
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush()
            level = min(len(heading.group(1)) + 1, 6)  # page <h1> is the convo title
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if _QUOTE.match(line):
            flush()
            block = []
            while i < len(lines) and (_QUOTE.match(lines[i]) or (block and lines[i].strip())):
                match = _QUOTE.match(lines[i])
                block.append(match.group(1) if match else lines[i])
                i += 1
            out.append("<blockquote>" + _blocks(block) + "</blockquote>")
            continue

        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush()
            rows = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            out.append(_render_table(rows))
            continue

        if _UL.match(line) or _OL.match(line):
            flush()
            block, base = [], _indent(line)
            ordered = bool(_OL.match(line))
            while i < len(lines):
                cur = lines[i]
                if not cur.strip():
                    # A blank line only stays inside the list if what follows is
                    # indented past the bullet, i.e. a continuation of an item.
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and _indent(lines[j]) > base:
                        block.extend(lines[i:j])
                        i = j
                        continue
                    break
                marker = _UL.match(cur) or _OL.match(cur)
                if _indent(cur) > base:
                    block.append(cur)
                elif marker and _indent(cur) == base and bool(_OL.match(cur)) == ordered:
                    block.append(cur)
                else:
                    break
                i += 1
            out.append(_render_list(block, base))
            continue

        para.append(line)
        i += 1

    flush()
    return "".join(out)


def _dedent(lines: list[str]) -> list[str]:
    """Strip the common leading indent, keeping relative nesting intact."""
    widths = [_indent(l) for l in lines if l.strip()]
    if not widths:
        return lines
    cut = min(widths)
    return [l[cut:] if l.strip() else l for l in lines]


def _render_list(lines: list[str], base: int) -> str:
    ordered = bool(_OL.match(lines[0]))
    items: list[list[str]] = []
    for line in lines:
        match = _UL.match(line) or _OL.match(line)
        if match and _indent(line) <= base:
            items.append([match.group(3)])
        elif items:
            items[-1].append(line)
        # A stray line before the first bullet is dropped rather than guessed at.
    tag = "ol" if ordered else "ul"
    rendered = []
    for item in items:
        item = [item[0]] + _dedent(item[1:])
        inner = _blocks(item)
        lead = re.match(r"<p>(.*?)</p>", inner, re.S)  # tight item: drop the leading <p>
        if lead and "<p>" not in lead.group(1):
            inner = lead.group(1) + inner[lead.end():]
        rendered.append(f"<li>{inner}</li>")
    return f"<{tag}>{''.join(rendered)}</{tag}>"
