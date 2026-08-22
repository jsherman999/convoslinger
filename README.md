# convoslinger — content

This branch holds **only** the published site and the conversations behind it.
The app that generates it lives on the `main` branch.

| Path | What it is |
|---|---|
| `docs/convos.json` | what the site shows — the whole management surface |
| `docs/index.html` | generated — the saved-convos index |
| `docs/convos/*.html` | generated — one page per visible conversation |
| `docs/assets/style.css` | the theme |
| `sources/` | the raw exports every page is generated from |
| `inbox/` | conversations dropped in from a phone, awaiting import |

GitHub Pages serves `docs/` from this branch directly (Settings → Pages →
*Deploy from a branch* → `site` → `/docs`). No workflow is involved in
deploying: pushing here is publishing. Everything under `docs/` is generated
from `sources/` plus `docs/convos.json` — don't hand-edit it; run
`./convo build` from the app checkout instead.

The split exists so that publishing a conversation and changing the app's code
can never collide on the same branch. See the `main` branch README for how to
set up the worktree and use the management app.
