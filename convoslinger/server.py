"""The management app: a small web UI for deciding what the site shows.

Binds to 127.0.0.1 by default. Every mutating request must carry the
`X-Convoslinger: 1` header, which forces a CORS preflight that this server
never answers — so a random web page you have open cannot drive it. Requests
carrying an `Origin` must also match the `Host` they were sent to.

Serving to the LAN (`--host 0.0.0.0`, for editing from a phone) additionally
requires a token on every request, because anyone who can reach the app can
publish to your public site. The token is generated once and kept in
`.manage-token` so a bookmarked URL keeps working across restarts.
"""

import http.cookies
import json
import mimetypes
import os
import secrets
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import gitops
from . import manifest as mf
from . import parse, render, site, summarize
from .paths import DOCS, ROOT, STATIC

MAX_BODY = 24 * 1024 * 1024  # a very long transcript is still only a few MB
COOKIE = "convoslinger_token"
TOKEN_FILE = ROOT / ".manage-token"
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def load_token(rotate: bool = False) -> str:
    """A stable per-checkout token, so a bookmarked phone URL keeps working."""
    if TOKEN_FILE.exists() and not rotate:
        existing = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(18)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return token


def lan_urls(port: int, token: str) -> list[str]:
    """Best-effort addresses this Mac is reachable at from a phone."""
    query = f"?k={token}" if token else ""
    urls = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # no packets sent; just picks a route
        urls.append(f"http://{probe.getsockname()[0]}:{port}/{query}")
    except OSError:
        pass
    finally:
        probe.close()
    name = socket.gethostname()
    if name and name not in ("localhost",):
        host = name if "." in name else f"{name}.local"  # Bonjour, on a Mac
        urls.append(f"http://{host}:{port}/{query}")
    return urls


class Handler(BaseHTTPRequestHandler):
    server_version = "convoslinger"
    TOKEN = ""  # empty = loopback only, no token required

    # ---- plumbing -------------------------------------------------------

    def log_message(self, fmt, *args):  # quieter than the default access log
        pass

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, fallback_type: str = "text/plain", set_cookie: bool = False) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or fallback_type
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie and Handler.TOKEN:
            # So the phone keeps working after navigating away from the ?k= URL.
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}={Handler.TOKEN}; Path=/; SameSite=Strict; Max-Age=31536000",
            )
        self.end_headers()
        self.wfile.write(body)

    def _token_ok(self) -> bool:
        """Token from the header, the ?k= query, or the cookie set on first visit."""
        if not Handler.TOKEN:
            return True
        if self.headers.get("X-Convoslinger-Token") == Handler.TOKEN:
            return True
        if parse_qs(urlparse(self.path).query).get("k", [""])[0] == Handler.TOKEN:
            return True
        raw = self.headers.get("Cookie")
        if raw:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
            if COOKIE in jar and jar[COOKIE].value == Handler.TOKEN:
                return True
        return False

    def _same_origin(self) -> bool:
        """A cross-site POST would carry an Origin that isn't the Host we answer on."""
        origin = self.headers.get("Origin")
        return not origin or urlparse(origin).netloc == self.headers.get("Host", "")

    def _read_json(self):
        if not self._token_ok():
            self._json({"error": "bad or missing token"}, 403)
            return None
        if self.headers.get("X-Convoslinger") != "1":
            self._json({"error": "missing X-Convoslinger header"}, 403)
            return None
        if not self._same_origin():
            self._json({"error": "bad origin"}, 403)
            return None
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json({"error": "request too large"}, 413)
            return None
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json({"error": "invalid JSON"}, 400)
            return None

    # ---- routes ---------------------------------------------------------

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if not self._token_ok():
            self.send_error(403, "Open the URL printed by `./convo manage`, token included")
            return None
        if path == "/":
            return self._file(STATIC / "index.html", set_cookie=True)
        if path in ("/app.js", "/style.css"):
            return self._file(STATIC / path.lstrip("/"))
        if path == "/api/state":
            return self._json(self.state())
        if path.startswith("/preview/"):
            return self.preview(path[len("/preview/"):])
        if path.startswith("/assets/"):
            # So a /preview/<id> page can resolve its ../assets/style.css.
            target = (DOCS / path.lstrip("/")).resolve()
            if not str(target).startswith(str((DOCS / "assets").resolve())):
                return self.send_error(403)
            return self._file(target)
        if path.startswith("/site/"):
            target = (DOCS / path[len("/site/"):]).resolve()
            if not str(target).startswith(str(DOCS.resolve())):
                return self.send_error(403)
            if target.is_dir():
                target = target / "index.html"
            return self._file(target)
        if path == "/site":
            self.send_response(302)
            self.send_header("Location", "/site/index.html")
            self.end_headers()
            return None
        return self.send_error(404)

    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        route = {
            "/api/save": self.save,
            "/api/import": self.do_import,
            "/api/inbox-import": self.inbox_import,
            "/api/delete": self.delete,
            "/api/publish": self.publish,
            "/api/describe": self.describe,
        }.get(path)
        if not route:
            return self.send_error(404)
        payload = self._read_json()
        if payload is None:
            return None
        try:
            return route(payload)
        except Exception as exc:  # surface the failure in the UI, keep serving
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ---- handlers -------------------------------------------------------

    def preview(self, convo_id: str):
        """Render a conversation on demand, including hidden ones.

        Hidden conversations have no page under docs/ by design, so this is the
        only way to read one back before deciding to publish it. Nothing is
        written to disk.
        """
        manifest = mf.load()
        entry = mf.find(manifest, convo_id)
        if not entry:
            return self.send_error(404)
        source = site.source_path(entry)
        if not source.exists():
            return self.send_error(404, "source file is missing")
        text = source.read_text(encoding="utf-8", errors="replace")
        if entry.get("format") == "html":
            page = text
        else:
            turns = parse.parse(text, source.name, entry.get("include_thinking", False))
            page = render.render_convo_page(entry, turns, manifest["site"])
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def state(self) -> dict:
        manifest = mf.load()
        ai_ok, ai_why = summarize.available()
        return {
            "site": manifest["site"],
            "convos": mf.display_order(manifest, include_hidden=True),
            "inbox": site.inbox_items(),
            "git": {
                "branch": gitops.branch(),
                "pending": gitops.pending(),
                "unpushed": gitops.unpushed(),
                "remote": gitops.remote_url(),
                "pages_url": gitops.pages_url(),
            },
            "ai": {"available": ai_ok, "reason": ai_why},
        }

    def save(self, payload: dict):
        manifest = mf.load()
        by_id = {c["id"]: c for c in manifest["convos"]}
        ordered = []
        for incoming in payload.get("convos", []):
            entry = by_id.get(incoming.get("id"))
            if not entry:
                continue
            for field in ("title", "synopsis", "date"):
                if incoming.get(field) is not None:
                    entry[field] = str(incoming[field]).strip()
            if incoming.get("tags") is not None:
                entry["tags"] = [str(t).strip() for t in incoming["tags"] if str(t).strip()]
            entry["visible"] = bool(incoming.get("visible", entry["visible"]))
            entry["pinned"] = bool(incoming.get("pinned", entry["pinned"]))
            ordered.append(entry)
        # Anything the UI didn't send (shouldn't happen) keeps its place at the end.
        ordered += [c for c in manifest["convos"] if c not in ordered]
        manifest["convos"] = ordered
        incoming_site = payload.get("site") or {}
        for field in ("title", "tagline", "footer", "sort"):
            if incoming_site.get(field) is not None:
                manifest["site"][field] = str(incoming_site[field]).strip()
        mf.save(manifest)
        result = site.build(manifest)
        return self._json({"ok": True, "built": result["built"], "problems": result["problems"], **self.state()})

    def do_import(self, payload: dict):
        entry, findings = site.import_text(
            payload.get("content", ""),
            payload.get("filename", ""),
            title=payload.get("title") or None,
            when=payload.get("date") or None,
            tags=payload.get("tags") or [],
            synopsis=payload.get("synopsis") if payload.get("synopsis") else None,
            scrub_secrets=payload.get("scrub", True),
            visible=payload.get("visible", True),
            include_thinking=payload.get("thinking", False),
            raw_html=payload.get("raw", False),
        )
        return self._json({"ok": True, "entry": entry, "findings": findings, **self.state()})

    def inbox_import(self, payload: dict):
        entry, findings = site.import_inbox_file(
            payload["file"],
            title=payload.get("title") or None,
            tags=payload.get("tags") or [],
            synopsis=payload.get("synopsis") if payload.get("synopsis") else None,
            scrub_secrets=payload.get("scrub", True),
            visible=payload.get("visible", True),
        )
        return self._json({"ok": True, "entry": entry, "findings": findings, **self.state()})

    def delete(self, payload: dict):
        ok = site.delete(payload.get("id", ""), drop_source=payload.get("drop_source", True))
        return self._json({"ok": ok, **self.state()})

    def publish(self, payload: dict):
        site.build()
        result = gitops.publish(payload.get("message", ""))
        # The phone gets one readable line; the full git output goes to the
        # terminal running the app, where there is room for it.
        print(f"\npublish: {result.get('summary', '')}\n{result.get('log', '')}\n")
        return self._json({**result, **self.state()})

    def describe(self, payload: dict):
        ok, why = summarize.available()
        if not ok:
            return self._json({"error": why}, 400)
        text = payload.get("content") or ""
        if payload.get("id"):
            entry = mf.find(mf.load(), payload["id"])
            if not entry:
                return self._json({"error": "unknown conversation"}, 404)
            text = site.source_path(entry).read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return self._json({"error": "nothing to summarise"}, 400)
        return self._json({"ok": True, **summarize.describe(text)})


def serve(
    port: int = 7788,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    rotate_token: bool = False,
) -> None:
    exposed = host not in LOOPBACK
    Handler.TOKEN = load_token(rotate_token) if exposed else ""

    httpd = ThreadingHTTPServer((host, port), Handler)
    local = f"http://127.0.0.1:{port}/"

    print("convoslinger manager   (ctrl-c to stop)")
    print(f"  this mac   {local}")
    if exposed:
        for url in lan_urls(port, Handler.TOKEN):
            print(f"  lan        {url}")
        print(f"\n  Anyone who opens a lan URL can edit and publish your site.")
        print(f"  Token is in .manage-token — `--new-token` rotates it.")
        print(f"  macOS may ask to allow incoming connections for python3; say yes.")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(local)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
