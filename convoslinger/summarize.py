"""Optional: let Claude write the synopsis for a conversation.

Entirely optional — convoslinger works without it, falling back to the first
few lines of the opening prompt. Enable with `pip install anthropic` and an
ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""

import json

MODEL = "claude-opus-5"
HEAD, TAIL = 30_000, 10_000

SYSTEM = """You write index-card summaries of saved Claude conversations for a \
personal, sparsely designed archive page.

Reply with JSON only, no prose around it, using exactly these keys:
  "title"    — under 60 characters, plain and specific, no trailing period
  "synopsis" — one sentence, under 200 characters, describing what was worked \
out; write it for someone deciding whether to open the page
  "tags"     — 1 to 3 short lowercase topic tags

Describe the conversation from the outside ("Debugging a flaky CI step..."), \
never address the reader, and never invent details that are not in the transcript."""


def available() -> tuple[bool, str]:
    """(usable, why-not) — checks the SDK is installed and credentials resolve."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "pip install anthropic to enable Claude-written synopses"
    import os

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True, ""
    from pathlib import Path

    if (Path.home() / ".config" / "anthropic").exists():
        return True, ""
    return False, "set ANTHROPIC_API_KEY, or run `ant auth login`"


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= HEAD + TAIL:
        return text, False
    return f"{text[:HEAD]}\n\n[... middle of transcript omitted ...]\n\n{text[-TAIL:]}", True


def describe(transcript: str) -> dict:
    """Return {'title', 'synopsis', 'tags', 'truncated'}; raises on API failure."""
    import anthropic

    body, truncated = _clip(transcript)
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": f"<transcript>\n{body}\n</transcript>"}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except ValueError:
        # Model returned prose instead of JSON — still usable as a synopsis.
        return {"title": "", "synopsis": text[:200], "tags": [], "truncated": truncated}
    return {
        "title": str(data.get("title", ""))[:80],
        "synopsis": str(data.get("synopsis", ""))[:280],
        "tags": [str(t).lower()[:24] for t in (data.get("tags") or [])][:3],
        "truncated": truncated,
    }
