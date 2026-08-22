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

./convo add examples/example-conversation.md   # import a conversation
./convo manage                                 # open the management app
```

One setup step, once: **Settings → Pages → Source: GitHub Actions**. From then
on the `Deploy site` workflow publishes `docs/` on every push to the default
branch, and pushing is publishing.

<sub>That one toggle can't be automated. Creating a Pages site requires
`administration:write`, a scope the workflow's `GITHUB_TOKEN` cannot hold, so
`actions/configure-pages` with `enablement: true` fails with *Resource not
accessible by integration*. Deploying to a site that already exists only needs
`pages:write`, which the workflow has. The settings page is web only — the
GitHub mobile app doesn't expose repository settings — but it works fine in a
phone browser.</sub>

---

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

One wrinkle: commits pushed by a workflow don't trigger other workflows, so
an ingested draft won't redeploy the site on its own. That's harmless — drafts
are hidden and don't change any published page — and your next push, or a
manual run of `Deploy site`, picks it up.

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
./convo manage          # http://127.0.0.1:7788
```

It binds to localhost only, and every write requires a custom header that a
cross-origin page cannot send, so a random tab you have open can't drive it.

What you can do without touching code:

- **Site** — the index title, tagline, footer (markdown allowed), and whether
  the list is ordered newest-first or by hand.
- **Add a conversation** — drop a file or paste text, set title / date / tags /
  synopsis, choose whether it publishes immediately.
- **Conversations** — for each one: `shown`, `pinned`, title, synopsis, date,
  tags, reorder, preview the real page (`↗`), delete (`✕`).
- **Save & rebuild** — writes `docs/convos.json` and regenerates every page.
- **Publish** — `git add` / `commit` / `push` on the current branch. The top
  bar tells you how many files are waiting.
- **✦** — if you have the `anthropic` SDK installed, asks Claude to write a
  title, synopsis and tags for that conversation. Optional; everything works
  without it.

<sub>The app never writes anywhere except `docs/`, `sources/`, and `inbox/`.</sub>

---

## How it fits together

Only two things are authoritative. Everything else is generated and safe to
delete:

| Path | What it is |
|---|---|
| `sources/<id>.md\|jsonl\|html` | the raw export, exactly as you saved it |
| `docs/convos.json` | what the site should show — the whole management surface |
| `docs/index.html` | **generated** — the saved-convos index |
| `docs/convos/<id>.html` | **generated** — one page per visible conversation |
| `docs/assets/style.css` | the theme, hand-edited if you want a different look |

Two workflows do the plumbing: `Deploy site` publishes `docs/` to Pages on
every push to the default branch, and `Ingest inbox` converts anything landing
in `inbox/` into a hidden draft.

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
./convo inbox            list inbox files    (--take <file>|all, --hidden)
./convo publish -m "…"   build, commit, push
./convo manage           the management app  (--port, --no-open)
./convo summary <id>     ask Claude for a title/synopsis (--apply to save)
```

## Optional: Claude-written synopses

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...      # or: ant auth login
```

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
