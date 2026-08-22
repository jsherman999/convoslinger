"""Catch credentials before they get published to a public web page."""

import re

PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("OpenAI-style API key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9]{20,}")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    (
        "assigned secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)"
            r"\s*[:=]\s*[\"']?([A-Za-z0-9_\-./+=]{12,})[\"']?"
        ),
    ),
]

REDACTED = "[redacted]"


def scan(text: str) -> list[dict]:
    """Report anything that looks like a credential, without changing the text."""
    hits = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text or ""):
            token = match.group(1) if match.groups() else match.group(0)
            hits.append(
                {
                    "kind": label,
                    "preview": token[:6] + "…" + token[-2:] if len(token) > 10 else "…",
                    "line": (text.count("\n", 0, match.start()) + 1),
                }
            )
    return hits


def scrub(text: str) -> tuple[str, list[dict]]:
    """Return the text with likely credentials replaced, plus what was found."""
    hits = scan(text)
    out = text or ""
    for label, pattern in PATTERNS:
        if pattern.groups:
            out = pattern.sub(lambda m: m.group(0).replace(m.group(1), REDACTED), out)
        else:
            out = pattern.sub(REDACTED, out)
    return out, hits
