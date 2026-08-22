"""Turn whatever you exported out of Claude into a list of conversation turns.

Handles three shapes:
  * markdown/plain text with speaker markers ("Human:", "## Claude", "You:", ...)
  * Claude Code session transcripts (.jsonl)
  * anything else — kept whole as a single block, still rendered as markdown
"""

import json
import re

ROLE_WORDS = {
    "human": "user",
    "user": "user",
    "you": "user",
    "me": "user",
    "prompt": "user",
    "q": "user",
    "assistant": "assistant",
    "claude": "assistant",
    "ai": "assistant",
    "answer": "assistant",
    "response": "assistant",
    "a": "assistant",
    "system": "system",
}

MARKER = re.compile(
    r"^\s{0,3}(?P<hash>\#{1,6}\s+)?(?P<open>\*\*|__)?\s*"
    r"(?P<role>human|user|you|me|prompt|assistant|claude|ai|answer|response|system|q|a)"
    r"\s*(?P<close>\*\*|__)?\s*(?P<colon>[:：])?\s*(?P<rest>.*?)\s*$",
    re.I,
)

TOOL_LIMIT = 1600


class Turn(dict):
    """{'role', 'kind', 'label', 'text'} — kind is 'md' or 'tool'."""


def turn(role: str, text: str, kind: str = "md", label: str | None = None) -> Turn:
    return Turn(role=role, kind=kind, label=label, text=text)


def detect_format(text: str, filename: str = "") -> str:
    name = (filename or "").lower()
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith((".html", ".htm")):
        return "html"
    head = (text or "").lstrip()[:400]
    if head.startswith("{") and '"' in head and "\n" in (text or ""):
        first = (text or "").lstrip().split("\n", 1)[0]
        try:
            obj = json.loads(first)
            if isinstance(obj, dict) and ("message" in obj or "type" in obj):
                return "jsonl"
        except ValueError:
            pass
    if head.lstrip().lower().startswith(("<!doctype html", "<html")):
        return "html"
    return "markdown"


def parse(text: str, filename: str = "", include_thinking: bool = False) -> list[Turn]:
    fmt = detect_format(text, filename)
    if fmt == "jsonl":
        return parse_jsonl(text, include_thinking=include_thinking)
    return parse_markdown(text)


def _marker_role(line: str):
    """Return the role this line announces, or None if it is ordinary prose."""
    match = MARKER.match(line)
    if not match:
        return None
    role = ROLE_WORDS.get(match.group("role").lower())
    if role is None:
        return None
    decorated = bool(match.group("hash") or match.group("open"))
    if match.group("colon"):
        return role, match.group("rest")
    # No colon: only a bare, decorated line ("## Claude", "**Human**") counts.
    if not match.group("rest") and decorated:
        return role, ""
    return None


def parse_markdown(text: str) -> list[Turn]:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    found: list[tuple[int, str, str]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        hit = _marker_role(line)
        if hit:
            found.append((i, hit[0], hit[1]))

    roles = {role for _, role, _ in found}
    if len(found) < 2 or not {"user", "assistant"} & roles:
        body = (text or "").strip()
        return [turn("note", body)] if body else []

    turns: list[Turn] = []
    preamble = "\n".join(lines[: found[0][0]]).strip()
    if preamble:
        turns.append(turn("note", preamble))
    for idx, (line_no, role, rest) in enumerate(found):
        end = found[idx + 1][0] if idx + 1 < len(found) else len(lines)
        body = "\n".join(([rest] if rest else []) + lines[line_no + 1 : end]).strip()
        if body:
            turns.append(turn(role, body))
    return turns


def _fence(payload: str, lang: str = "") -> str:
    payload = payload if len(payload) <= TOOL_LIMIT else payload[:TOOL_LIMIT] + "\n… truncated"
    return f"```{lang}\n{payload}\n```"


def parse_jsonl(text: str, include_thinking: bool = False) -> list[Turn]:
    """Parse a Claude Code session transcript, skipping records we don't recognise."""
    turns: list[Turn] = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("message")
        role = (message or {}).get("role") if isinstance(message, dict) else record.get("role")
        role = role or record.get("type")
        if role not in ("user", "assistant"):
            continue
        content = message.get("content") if isinstance(message, dict) else record.get("content")
        if isinstance(content, str):
            if content.strip():
                turns.append(turn(role, content.strip()))
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and (block.get("text") or "").strip():
                turns.append(turn(role, block["text"].strip()))
            elif btype == "thinking" and include_thinking and (block.get("thinking") or "").strip():
                turns.append(turn("thinking", block["thinking"].strip()))
            elif btype == "tool_use":
                payload = json.dumps(block.get("input", {}), indent=2, ensure_ascii=False)
                turns.append(turn("tool", _fence(payload, "json"), "tool", f"{block.get('name', 'tool')}"))
            elif btype == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = "\n".join(
                        b.get("text", "") for b in body if isinstance(b, dict) and b.get("type") == "text"
                    )
                body = (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).strip()
                if body:
                    turns.append(turn("tool", _fence(body), "tool", "result"))
    return _merge_adjacent(turns)


def _merge_adjacent(turns: list[Turn]) -> list[Turn]:
    """Claude Code splits one reply across records; stitch text runs back together."""
    merged: list[Turn] = []
    for item in turns:
        if merged and item["kind"] == "md" == merged[-1]["kind"] and item["role"] == merged[-1]["role"]:
            merged[-1]["text"] += "\n\n" + item["text"]
        else:
            merged.append(item)
    return merged


def first_prompt(turns: list[Turn]) -> str:
    for item in turns:
        if item["role"] in ("user", "note") and item["kind"] == "md":
            return item["text"]
    return turns[0]["text"] if turns else ""


def auto_title(turns: list[Turn], fallback: str = "Untitled conversation") -> str:
    text = re.sub(r"```.*?```", " ", first_prompt(turns), flags=re.S)
    text = re.sub(r"[#>*_`\[\]]", "", text).strip()
    line = next((l.strip() for l in text.split("\n") if l.strip()), "")
    if not line:
        return fallback
    line = re.split(r"(?<=[.!?])\s", line)[0]
    return (line[:70].rstrip() + "…") if len(line) > 70 else line


def auto_synopsis(turns: list[Turn], limit: int = 240, skip: str = "") -> str:
    """A no-API fallback synopsis: the opening ask, flattened."""
    text = re.sub(r"```.*?```", " ", first_prompt(turns), flags=re.S)
    text = re.sub(r"[#>*_`]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    head = skip.rstrip("…").strip()
    if head and text.lower().startswith(head.lower()):
        remainder = text[len(head):].strip(" .")
        text = remainder or text
    return (text[: limit - 1].rstrip() + "…") if len(text) > limit else text
