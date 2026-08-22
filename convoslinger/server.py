"""The management app: a small local web UI for deciding what the site shows.

Binds to 127.0.0.1 only. Every mutating request must carry the
`X-Convoslinger: 1` header, which forces a CORS preflight that this server
never answers — so a random web page you have open cannot drive it.
"""

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import gitops
from . import manifest as mf
from . import site, summarize
from .paths import DOCS, STATIC

MAX_BODY = 24 * 1024 * 1024  # a very long transcript is still only a few MB


class Handler(BaseHTTPRequestHandler):
    server_version = "convoslinger"

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

    def _file(self, path, fallback_type: str = "text/plain") -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or fallback_type
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        if self.headers.get("X-Convoslinger") != "1":
            self._json({"error": "missing X-Convoslinger header"}, 403)
            return None
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
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
        if path == "/":
            return self._file(STATIC / "index.html")
        if path in ("/app.js", "/style.css"):
            return self._file(STATIC / path.lstrip("/"))
        if path == "/api/state":
            return self._json(self.state())
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


def serve(port: int = 7788, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"convoslinger manager on {url}   (ctrl-c to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
