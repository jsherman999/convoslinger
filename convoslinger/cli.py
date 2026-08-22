"""Command line front end.  Run `./convo --help`."""

import argparse
import sys
from pathlib import Path

from . import gitops
from . import manifest as mf
from . import site, summarize


def _tags(value: str) -> list:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def _report(entry: dict, findings: list) -> None:
    print(f"added  {entry['id']}")
    print(f"       {entry['title']}")
    if entry["synopsis"]:
        print(f"       {entry['synopsis']}")
    print(f"       docs/{entry['path']}  ({'visible' if entry['visible'] else 'hidden'})")
    if findings:
        kinds = ", ".join(sorted({f['kind'] for f in findings}))
        print(f"  !    {len(findings)} possible secret(s) found and redacted: {kinds}")


def cmd_add(args) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    entry, findings = site.import_text(
        path.read_text(encoding="utf-8", errors="replace"),
        path.name,
        title=args.title,
        when=args.date,
        tags=_tags(args.tags),
        synopsis=args.synopsis,
        scrub_secrets=not args.keep_secrets,
        visible=not args.hidden,
        include_thinking=args.thinking,
        raw_html=args.raw,
    )
    _report(entry, findings)
    return 0


def cmd_list(args) -> int:
    manifest = mf.load()
    items = mf.display_order(manifest, include_hidden=True)
    if not items:
        print("no conversations yet — try `./convo add <file>`")
        return 0
    for entry in items:
        flags = ("*" if entry["pinned"] else " ") + (" " if entry["visible"] else "h")
        print(f"{flags} {entry['date']}  {entry['id']}")
        print(f"     {entry['title']}")
    print(f"\n{sum(1 for c in items if c['visible'])} visible / {len(items)} total")
    return 0


def _set(convo_id: str, **changes) -> int:
    manifest = mf.load()
    entry = mf.find(manifest, convo_id)
    if not entry:
        print(f"unknown conversation: {convo_id}", file=sys.stderr)
        return 1
    entry.update({k: v for k, v in changes.items() if v is not None})
    mf.save(manifest)
    site.build(manifest)
    print(f"updated {convo_id}")
    return 0


def cmd_show(args) -> int:
    return _set(args.id, visible=True)


def cmd_hide(args) -> int:
    return _set(args.id, visible=False)


def cmd_pin(args) -> int:
    return _set(args.id, pinned=not args.off)


def cmd_edit(args) -> int:
    return _set(
        args.id,
        title=args.title,
        synopsis=args.synopsis,
        date=args.date,
        tags=_tags(args.tags) if args.tags is not None else None,
    )


def cmd_rm(args) -> int:
    if not site.delete(args.id, drop_source=not args.keep_source):
        print(f"unknown conversation: {args.id}", file=sys.stderr)
        return 1
    print(f"removed {args.id}")
    return 0


def cmd_build(args) -> int:
    result = site.build()
    for problem in result["problems"]:
        print(f"  !    {problem}", file=sys.stderr)
    print(f"built {result['built']} page(s) + docs/index.html")
    return 1 if result["problems"] else 0


def cmd_inbox(args) -> int:
    items = site.inbox_items()
    if args.take:
        names = [i["file"] for i in items] if args.take == "all" else [args.take]
        for name in names:
            entry, findings = site.import_inbox_file(name, visible=not args.hidden)
            _report(entry, findings)
        return 0
    if not items:
        print("inbox is empty")
        return 0
    for item in items:
        warn = f"  ! {item['secrets']} possible secret(s)" if item["secrets"] else ""
        print(f"{item['file']}  ({item['bytes']} bytes){warn}")
        print(f"     {item['suggested_title']}")
    print("\nimport with `./convo inbox --take <file>` or `--take all`")
    return 0


def cmd_publish(args) -> int:
    site.build()
    result = gitops.publish(args.message)
    print(result["log"])
    if result.get("ok") and not result.get("nothing_to_do"):
        url = gitops.pages_url()
        if url:
            print(f"\nlive shortly at {url}")
    return 0 if result.get("ok") else 1


def cmd_manage(args) -> int:
    from .server import serve

    serve(
        port=args.port,
        host="0.0.0.0" if args.lan else args.host,
        open_browser=not args.no_open,
        rotate_token=args.new_token,
    )
    return 0


def cmd_summary(args) -> int:
    ok, why = summarize.available()
    if not ok:
        print(why, file=sys.stderr)
        return 1
    manifest = mf.load()
    entry = mf.find(manifest, args.id)
    if not entry:
        print(f"unknown conversation: {args.id}", file=sys.stderr)
        return 1
    text = site.source_path(entry).read_text(encoding="utf-8", errors="replace")
    described = summarize.describe(text)
    print(f"title:    {described['title']}")
    print(f"synopsis: {described['synopsis']}")
    print(f"tags:     {', '.join(described['tags'])}")
    if args.apply:
        return _set(
            args.id,
            title=described["title"] or None,
            synopsis=described["synopsis"] or None,
            tags=described["tags"] or None,
        )
    print("\nre-run with --apply to save these")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="convo", description="publish saved Claude conversations")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="import a saved conversation (.md/.txt/.jsonl/.html)")
    add.add_argument("file")
    add.add_argument("--title")
    add.add_argument("--synopsis")
    add.add_argument("--date", help="YYYY-MM-DD (defaults to today)")
    add.add_argument("--tags", default="", help="comma separated")
    add.add_argument("--hidden", action="store_true", help="import without publishing it")
    add.add_argument("--keep-secrets", action="store_true", help="skip credential redaction")
    add.add_argument("--thinking", action="store_true", help="keep thinking blocks (.jsonl)")
    add.add_argument("--raw", action="store_true", help="publish an .html file completely untouched")
    add.set_defaults(func=cmd_add)

    listing = sub.add_parser("list", help="list every conversation")
    listing.set_defaults(func=cmd_list)

    for name, func, helptext in (
        ("show", cmd_show, "publish a conversation"),
        ("hide", cmd_hide, "unpublish a conversation (page is removed, source kept)"),
    ):
        cmd = sub.add_parser(name, help=helptext)
        cmd.add_argument("id")
        cmd.set_defaults(func=func)

    pin = sub.add_parser("pin", help="keep a conversation at the top of the index")
    pin.add_argument("id")
    pin.add_argument("--off", action="store_true")
    pin.set_defaults(func=cmd_pin)

    edit = sub.add_parser("edit", help="change title/synopsis/date/tags")
    edit.add_argument("id")
    edit.add_argument("--title")
    edit.add_argument("--synopsis")
    edit.add_argument("--date")
    edit.add_argument("--tags")
    edit.set_defaults(func=cmd_edit)

    remove = sub.add_parser("rm", help="delete a conversation entirely")
    remove.add_argument("id")
    remove.add_argument("--keep-source", action="store_true")
    remove.set_defaults(func=cmd_rm)

    build = sub.add_parser("build", help="regenerate docs/ from convos.json")
    build.set_defaults(func=cmd_build)

    inbox = sub.add_parser("inbox", help="list or import files dropped in inbox/")
    inbox.add_argument("--take", help="a filename, or 'all'")
    inbox.add_argument("--hidden", action="store_true")
    inbox.set_defaults(func=cmd_inbox)

    publish = sub.add_parser("publish", help="build, commit and push")
    publish.add_argument("-m", "--message", default="")
    publish.set_defaults(func=cmd_publish)

    manage = sub.add_parser("manage", help="open the management app in a browser")
    manage.add_argument("--port", type=int, default=7788)
    manage.add_argument("--host", default="127.0.0.1", help="bind address")
    manage.add_argument("--lan", action="store_true", help="serve to the LAN (phone), token required")
    manage.add_argument("--new-token", action="store_true", help="rotate the LAN token")
    manage.add_argument("--no-open", action="store_true")
    manage.set_defaults(func=cmd_manage)

    describe = sub.add_parser("summary", help="have Claude write a title/synopsis (needs anthropic SDK)")
    describe.add_argument("id")
    describe.add_argument("--apply", action="store_true")
    describe.set_defaults(func=cmd_summary)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
