"""Thin wrappers over git, used by the CLI and the management app."""

import re
import subprocess

from .paths import ROOT

TRACKED = ["docs", "sources", "inbox"]


def _run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def branch() -> str:
    code, out = _run(["branch", "--show-current"])
    return out if code == 0 and out else "HEAD"


def remote_url() -> str:
    code, out = _run(["remote", "get-url", "origin"])
    return out if code == 0 else ""


def pending() -> list[str]:
    code, out = _run(["status", "--porcelain", "--", *TRACKED])
    return [line for line in out.splitlines() if line.strip()] if code == 0 else []


def pages_url() -> str:
    """Guess the GitHub Pages URL from the origin remote."""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url())
    if not match:
        return ""
    owner, repo = match.group(1), match.group(2)
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner.lower()}.github.io/"
    return f"https://{owner.lower()}.github.io/{repo}/"


def publish(message: str = "") -> dict:
    """Stage the site, commit, and push the current branch."""
    steps = []
    if not pending():
        return {"ok": True, "nothing_to_do": True, "log": "Nothing to publish — working tree is clean."}

    code, out = _run(["add", "--", *TRACKED])
    steps.append(out)
    if code != 0:
        return {"ok": False, "log": "\n".join(filter(None, steps))}

    code, out = _run(["commit", "-m", message.strip() or "Update saved conversations"])
    steps.append(out)
    if code != 0:
        return {"ok": False, "log": "\n".join(filter(None, steps))}

    code, out = _run(["push", "-u", "origin", branch()])
    steps.append(out)
    return {"ok": code == 0, "log": "\n".join(filter(None, steps))}
