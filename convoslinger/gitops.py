"""Thin wrappers over git, used by the CLI and the management app."""

import re
import subprocess

from .paths import CONTENT

TRACKED = ["docs", "sources", "inbox"]


def _run(args: list[str]) -> tuple[int, str]:
    """Run git where the content lives — the site worktree, not the app checkout."""
    if not CONTENT.is_dir():
        return 1, f"content directory not found: {CONTENT}"
    try:
        proc = subprocess.run(
            ["git", *args], cwd=CONTENT, capture_output=True, text=True, timeout=180
        )
    except OSError as exc:
        return 1, f"could not run git in {CONTENT}: {exc}"
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


def unpushed() -> int:
    """Commits made here that the remote hasn't got — e.g. after a rejected push."""
    code, out = _run(["rev-list", "--count", f"origin/{branch()}..HEAD"])
    try:
        return int(out) if code == 0 else 0
    except ValueError:
        return 0


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
    """Stage the site, commit, and push — rebasing onto the remote if needed.

    Returns {ok, summary, log}: `summary` is one line fit for a phone toast,
    `log` is the full git output for the terminal.
    """
    steps: list[str] = []
    current = branch()

    def result(ok: bool, summary: str, **extra) -> dict:
        return {"ok": ok, "summary": summary, "log": "\n".join(filter(None, steps)), **extra}

    behind_only = not pending() and unpushed() > 0
    if not pending() and not behind_only:
        return result(True, "Nothing to publish — the site is already up to date.", nothing_to_do=True)

    # A clean tree with unpushed commits means a previous push was rejected;
    # there is nothing new to commit, but there is still something to push.
    if not behind_only:
        code, out = _run(["add", "--", *TRACKED])
        steps.append(out)
        if code != 0:
            return result(False, "Could not stage the site files.")

        code, out = _run(["commit", "-m", message.strip() or "Update saved conversations"])
        steps.append(out)
        if code != 0:
            return result(False, "Commit failed.")

    code, out = _run(["push", "-u", "origin", current])
    steps.append(out)
    if code == 0:
        return result(True, "Published.")

    # Someone else pushed to this branch first — very normal when the repo also
    # carries the app's own code. Replay this commit on top and push again.
    if "fetch first" not in out and "non-fast-forward" not in out and "rejected" not in out:
        return result(False, "Push failed — see the terminal for git's output.")

    steps.append("--- remote moved ahead, rebasing ---")
    code, out = _run(["fetch", "origin", current])
    steps.append(out)
    if code != 0:
        return result(False, "Could not reach the remote. Check the network and press Publish again.")

    code, out = _run(["rebase", "--autostash", f"origin/{current}"])
    steps.append(out)
    if code != 0:
        _run(["rebase", "--abort"])
        return result(
            False,
            "The remote changed the same files. Your work is committed but not pushed — "
            "run `git pull --rebase` in the repo and sort out the conflict, then Publish again.",
            conflict=True,
        )

    code, out = _run(["push", "-u", "origin", current])
    steps.append(out)
    if code != 0:
        return result(False, "Rebased onto the remote, but the push still failed. See the terminal.")
    return result(True, "Published (after pulling in newer changes from the remote).", rebased=True)
