# convoslinger

Save a Claude conversation from your phone, turn it into a dark, readable HTML
page, and publish it to GitHub Pages alongside a sparse index of everything
you've kept — **saved convos**.

You decide what appears on that index from a small management app that runs on
your Mac. No recoding, no template editing: you toggle a checkbox and hit
Publish.

```
phone  ──▶  inbox/ or a file  ──▶  ./convo manage  ──▶  docs/  ──▶  GitHub Pages
                                    (title, synopsis,
                                     shown/hidden, publish)
```

- **Index:** `https://<you>.github.io/convoslinger/`
- **A conversation:** `https://<you>.github.io/convoslinger/convos/2026-08-22-some-slug.html`

Everything here is Python standard library and vanilla JS. There is nothing to
`npm install`, no static-site generator, and no build step.

---

## Quick start

```bash
git clone https://github.com/jsherman999/convoslinger
cd convoslinger
./convo content --setup
./convo add examples/example-conversation.md
./convo manage
```

That checks out the conversations, imports an example, and opens the
management app.

One setup step, once: **Settings → Pages → Source: Deploy from a branch →
`site` → `/docs`**. After that, pushing to `site` is publishing — no workflow
in the loop.

## Two branches

The app's code and the conversations it publishes live on separate branches,
because they change for unrelated reasons and used to collide on every push:

| Branch | Holds |
|---|---|
| the default branch | the app — `convo`, `convoslinger/`, `tests/` |
| `site` | `docs/`, `sources/`, `inbox/` — the published site and its sources |

`./convo content --setup` checks `site` out as a **git worktree** at
`content/`, inside the app checkout:

```
convoslinger/          the app
  content/             worktree of `site` — gitignored here
    docs/  sources/  inbox/
```

One clone, one `.git`, both branches checked out at once. Everything the app
writes goes to `content/`, and Publish commits and pushes the `site` branch
only — so publishing a conversation can never reject a code push, or vice
versa. `./convo content` prints where things are; `CONVOSLINGER_CONTENT` puts
the content anywhere you like. With neither, the app falls back to using the
repository root, which is the old single-directory layout.

<sub>Pages deploys straight from the branch rather than through Actions
because the `github-pages` environment only permits deployments from the
repository's default branch — a workflow deploying from `site` fails before
its first step. Branch-source has no such restriction, and it means a push
from the management app publishes with nothing in between.</sub>

---

### Moving an existing checkout to the split layout

If you cloned before the split, your checkout still has `docs/` and `sources/`
next to the code. **Publish anything outstanding first** — the migration
deletes those directories from the code branch:

```bash
./convo publish
git pull --rebase
./convo content --setup
./convo content
```

In order: publish anything still unpushed, pull the removal and the new code,
bring the conversations back at `content/`, and confirm — the last command
should report `branch site`.

Nothing is lost either way: the conversations moved to the `site` branch, and
the old commits still contain them.

## Getting a conversation off your phone

Three routes, in increasing order of convenience. All of them end with a file
that `./convo add` or the management app understands.

### 1. Share the text (works today, no setup)

In the Claude app, open the conversation, share or copy it, and get the text to
your Mac however you like — AirDrop, Notes, a message to yourself. Save it as
`.md` or `.txt`, then drop it onto the management app's **Add a conversation**
panel, or paste it straight into the text box.

convoslinger looks for speaker markers (`Human:`, `Assistant:`, `You:`,
`## Claude`, …) and splits the transcript into turns. If it can't find any, it
keeps the whole thing as a single block and still renders the markdown — you
never lose content to a parsing failure.

**Copying from the Claude app gives you one message — Claude's reply — not the
whole exchange.** Your question isn't in it, so there are no speaker markers to
find, and a title guessed from that text is the first sentence of an answer
("Yes — almost all modern floating docks are sectional…"). Paste what you asked
into the **Your question** box when you import (or `--prompt` from the CLI) and
the page becomes a proper exchange, with the title and synopsis taken from the
question instead. It's stored in `convos.json`, not edited into your export, so
`sources/` stays exactly as the app gave it to you and you can fix the wording
later with `./convo edit --prompt`.

Worth checking the preview either way: the app's copy also drops some
structured content — a list of dealers in one of mine came through as a
heading with nothing under it.

### 2. Save an HTML file and publish it as-is

Already have an `.html` file — from a share sheet, a print-to-file, or anywhere
else? Add it the same way. convoslinger copies it verbatim, adds a small
"← all conversations" bar at the top, and lists it on the index. Pass `--raw`
(or leave the file untouched from the CLI) if you don't even want that bar.

### 3. An iOS Shortcut that commits straight to the repo

This is the one that makes the phone self-sufficient. Build a shortcut that
accepts text from the share sheet and PUTs it to the GitHub contents API:

| Step | Action |
|---|---|
| 1 | **Receive** Text from *Share Sheet* |
| 2 | **Ask for Input** → Text, prompt "Title" |
| 3 | **Text** → `<Shortcut Input>` (this is the file body) |
| 4 | **Base64 Encode** the text from step 3 |
| 5 | **Get contents of URL** |

Configure step 5 as:

- **URL:** `https://api.github.com/repos/<you>/convoslinger/contents/inbox/[Current Date, formatted yyyy-MM-dd-HHmm]-[Title].md`
- **Method:** `PUT`
- **Headers:** `Authorization: Bearer <fine-grained PAT>`, `Accept: application/vnd.github+json`
- **Request body** (JSON):
  - `message` → `convo from phone`
  - `content` → the Base64 result from step 4

Create the token at **GitHub → Settings → Developer settings → Fine-grained
tokens**, scoped to *only* this repository with **Contents: read and write**.
Nothing else. Treat it like a password — it lives in the shortcut on your
phone.

The `Ingest inbox` GitHub Action then converts anything landing in `inbox/`
into a **hidden** draft and commits it. Hidden means exactly that: it is not on
the index and its page is not generated. You review it on the Mac and flip it
to shown when you want it public.

Prefer to keep the Action out of it? Delete
`.github/workflows/ingest-inbox.yml`, `git pull` on the Mac, and the
management app will show whatever is sitting in `inbox/` with an **import**
button next to it.

### Claude Code sessions

Claude Code writes each session as a `.jsonl` transcript under
`~/.claude/projects/<project>/`. Point `./convo add` at one directly:

```bash
./convo add ~/.claude/projects/-Users-you-myproject/abc123.jsonl
```

Tool calls and their results render as collapsed `› tool` disclosures, so the
page reads as a conversation rather than a log dump. Thinking blocks are
dropped unless you pass `--thinking`.

---

## The management app

```bash
./convo manage
```

It serves at `http://127.0.0.1:7788`.

It binds to localhost only, and every write requires a custom header that a
cross-origin page cannot send, so a random tab you have open can't drive it.

What you can do without touching code:

- **Site** — the index title, tagline, footer (markdown allowed), and whether
  the list is ordered newest-first or by hand.
- **Add a conversation** — drop a file or paste text, set title / date / tags /
  synopsis, choose whether it publishes immediately.
- **Conversations** — for each one: `shown`, `pinned`, title, synopsis, date,
  tags, reorder, delete (`✕`), and `↗` to read it: the published page if it's
  shown, or a rendered-on-demand preview if it's hidden. That preview is the
  point of importing hidden first — you get to see exactly what would go public
  before it does, and nothing is written to `docs/` until you publish.
- **Save & rebuild** — writes `docs/convos.json` and regenerates every page.
- **Publish** — `git add` / `commit` / `push` on the current branch. The top
  bar shows both what's changed and any commits still waiting to be pushed.

  If someone else pushed to the branch first — likely, since this repo holds
  the app's own code as well as your conversations — the push is rejected,
  and Publish fetches, replays your commit on top, and pushes again by itself.
  You only have to step in when both sides changed the same file; then it says
  so, leaves your commit intact, and you resolve it with `git pull --rebase`.
  A push that was rejected earlier is retried on the next Publish even though
  there is nothing new to commit.
- **✦** — if you have the `anthropic` SDK installed, asks Claude to write a
  title, synopsis and tags for that conversation. Optional; everything works
  without it.

<sub>The app never writes anywhere except `docs/`, `sources/`, and `inbox/`.</sub>

### Using it from your phone

```bash
./convo manage --lan
```

That binds to every interface instead of loopback and prints the URLs to open,
including your Mac's Bonjour name (`http://your-mac.local:7788/?k=…`), which
survives a DHCP lease change in a way the IP doesn't. macOS will ask whether to
allow incoming connections for `python3` the first time — say yes. Both
machines have to be on the same network; this is a LAN thing, not something
reachable from outside the house.

Because anyone who can reach the app can publish to your public site, `--lan`
requires a token. It's generated once, stored in `.manage-token` (gitignored),
and included in the printed URL, so bookmark that URL on the phone and it keeps
working across restarts. The server also sets it as a cookie on first visit.
`--new-token` rotates it and invalidates the old bookmark.

Loopback is unchanged: plain `./convo manage` needs no token, since only your
Mac can reach it. `--host <address>` binds somewhere specific if you'd rather
not listen on all interfaces.

<sub>The token is the only thing standing between your LAN and your published
site, and it travels over plain HTTP — fine on a home network, not something to
run on café wifi. Stop the server when you're done rather than leaving it up.</sub>

---

## How it fits together

Only two things are authoritative. Everything else is generated and safe to
delete:

All paths below are inside `content/` (the `site` branch):

| Path | What it is |
|---|---|
| `sources/<id>.md\|jsonl\|html` | the raw export, exactly as you saved it |
| `docs/convos.json` | what the site should show — the whole management surface |
| `docs/index.html` | **generated** — the saved-convos index |
| `docs/convos/<id>.html` | **generated** — one page per visible conversation |
| `docs/assets/style.css` | the theme, hand-edited if you want a different look |

One workflow does the plumbing: `Ingest inbox`, on the `site` branch, converts
anything landing in `inbox/` into a hidden draft. It checks the app out beside
the content to do it. Deploying needs no workflow at all.

`./convo build` regenerates `docs/` from those two inputs. That means you can
edit `docs/convos.json` by hand — on the Mac, or straight on github.com from
your phone — and rebuild. The management app is a nicer front end to that one
file, not a separate source of truth.

Because pages are generated, **hiding a conversation removes its page**, not
just its index entry. The URL stops working at the current commit. Git history
still contains it, so treat "hidden" as unlisted-and-unreachable rather than
as a privacy guarantee — if you published something you shouldn't have, rewrite
history or make the repo private.

### Before you publish

Every import is scanned for things that look like credentials — Anthropic and
OpenAI-style keys, GitHub tokens, AWS key ids, JWTs, private key blocks, and
`password = …` style assignments. They're replaced with `[redacted]` and you
get a count of what was caught. Pass `--keep-secrets` to skip it, and read the
page before publishing either way: a scanner catches patterns, not judgement.

---

## Command line

This block is a reference listing, not something to paste.

```
./convo add <file>       import a .md / .txt / .jsonl / .html conversation
                           --title --synopsis --date --tags a,b
                           --hidden          import without publishing
                           --keep-secrets    skip credential redaction
                           --thinking        keep thinking blocks (.jsonl)
                           --raw             publish an .html file untouched
./convo list             every conversation, `h` marks hidden, `*` pinned
./convo show <id>        publish it
./convo hide <id>        unpublish it (page removed, source kept)
./convo pin <id>         keep it at the top   (--off to unpin)
./convo edit <id>        --title --synopsis --date --tags
./convo rm <id>          delete it and its source
./convo build            regenerate docs/ from convos.json
./convo content          where the conversations live  (--setup adds the worktree)
./convo inbox            list inbox files    (--take <file>|all, --hidden)
./convo publish -m "…"   build, commit, push
./convo manage           the management app  (--port, --no-open)
                           --lan             serve to the LAN, token required
                           --host <addr>     bind somewhere specific
                           --new-token       rotate the LAN token
./convo summary <id>     ask Claude for a title/synopsis (--apply to save)
```

## Optional: Claude-written synopses

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
```

Or run `ant auth login` instead of exporting a key.

`./convo summary <id>` and the ✦ button then return a title, a one-sentence
synopsis and a couple of tags. Nothing is saved until you save it, and the
whole feature is skippable — without it you get the opening lines of your first
message as a fallback synopsis, which you can edit in the app.

## Tests

```bash
python3 -m unittest discover -s tests
```

Covers the parts most likely to break quietly: the markdown renderer's
escaping, speaker detection (including "You should…" not being mistaken for a
turn), Claude Code `.jsonl` parsing, credential redaction, and index ordering.

## Making it look different

`docs/assets/style.css` is one plain stylesheet with the palette at the top:

```css
--bg: #0c0c0d;  --fg: #e9e7e4;  --muted: #8a8781;  --accent: #d98a6a;
```

Change those four and re-run `./convo build`. The page structure is
`.item` rows on the index and `.turn.user` / `.turn.assistant` articles on a
conversation page.
