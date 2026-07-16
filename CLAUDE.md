# SetTheory — context for Claude

The map a dig starts from. Pick the colour you're feeling, hear what you already
own in it, see the labels that colour lives on, walk one, write down what it
sounded like. See `README.md` for the user-facing story.

Built to mirror **Sessions** (`~/Documents/GitHub/Sessions`) deliberately — same
spine, same storage contract, same dev tooling — so the two can merge later if
this earns it. The parked merge argument lives in `Sessions/IDEAS.md`; read it
before proposing integration.

## Principles

- **Plain Markdown is the only user storage.** `~/Documents/SetTheory/labels.md`,
  human-readable and hand-editable. The map (`.cache/data.json`) is *derived* and
  rebuildable; your notes are the only thing here that can't be regenerated.
- **The server never touches the network.** `build.py` does, alone and on purpose.
  Keep that line — the app must stay usable when Bandcamp breaks, and Bandcamp
  *will* break (see below).
- **No AI.** Nothing generates, ranks, suggests, or recommends. Every judgment in
  it is one the user made.
- **The empty cells are the point.** If Blue has no `++++`, that cell renders and
  says so. Absence is invisible in a list and only visible on a grid — that's the
  one thing this does that Rekordbox structurally cannot. Never hide an empty cell.
- **Show, don't prescribe.** A gap isn't a need. Never tell the user to fill one.
- **`textContent`, never `innerHTML`,** on label names, notes, or anything from
  Bandcamp. Not cosmetic — see the O'Flynn bug below.

## Where the rules differ from Sessions (knowingly)

Sessions promises no dependencies and that nothing leaves the machine. This breaks
both, which is exactly why it's a separate repo:

- **ffmpeg** — 109 of the user's 140 tracks are AIFF and browsers won't play them.
- **Bandcamp's undocumented API** — `build.py` only. `api/fancollection`,
  `api/mobile/24/band_details`, and the `data-blob` on a fan page are not public
  contracts and will break without notice. When they do, the app still runs on the
  last `.cache/data.json`; only a rebuild fails. Keep that property.

## Run / build

```sh
./dev.sh                 # ALWAYS use this while working — port 4398, throwaway notes
./dev.sh stop | fresh
./devbrowser.py '<js>'   # drive the real DOM; frontend claims need this, not a reading
python3 build.py https://bandcamp.com/YOURNAME   # rebuild the map (cached; re-runs are fast)
./install.sh             # one-time: builds SetTheory.app
./update.sh              # pull + stop the server so new logic takes effect
```

`dev.sh` hard-wires port **4398** and `.devdata/`, so it cannot reach the real app
on **4322** or the real `labels.md`. Stopping goes by recorded PID, never by
process name — `pkill -f settheory.py` would also match a real server, and that
class of mistake took Sessions' app down once.

## Architecture

**`build.py`** — the network half. Joins three sources into `.cache/data.json`:
a Rekordbox XML export, a folder of `<Colour> <energy>.m3u8` cell playlists, and
the user's Bandcamp collection. Configurable via `SETTHEORY_XML`,
`SETTHEORY_CELLS`, `SETTHEORY_FAN`. Everything it fetches is cached in `.cache/`.

Two non-obvious things it rests on, both load-bearing:
- **Rekordbox's `Label` field is useless here** — 13 of 140 tracks have one. Labels
  come from Bandcamp, matched on normalized artist + album (~69%; the misses are
  files with blank tags, not join failures).
- **`selling_band_id` is the label** when it differs from `band_id`. That's what
  collapses scattered artist pages back into the label that sold them.
  `band_details` also returns `discography` — the denominator behind "1 of 28
  releases".

**`settheory.py`** — single-file stdlib server, port 4322 (`SETTHEORY_PORT`).
- `parse_labels()` / `render_labels()` — regex over a known Markdown convention:
  `## Name` sections, `**Field:** value` (last-wins, like Sessions), free prose
  below. `ensure_data_dir()` seeds from `defaults/` on first run.
- `/api/state` merges the derived map with `labels.md`. `/api/label` is the only
  write. `/audio?id=N` transcodes AIFF→MP3 once, caches, serves with Range so
  scrubbing works; `prewarm()` warms the cache in a background thread on boot.

**`app/`** — vanilla, no build step. `index.html` is sections toggled by `render()`;
`app.js` builds DOM nodes and attaches listeners; `style.css` is **dark only**, and
**the colour you pick is the only light in the room** (`data-color` on `#app` sets
`--area`, inherited by every accent).

**`SetTheory.app`** — the Dock icon, built by `make-app.sh` (gitignored; it bakes an
absolute path, so it's per-machine). **The click is the only maintenance there is**,
and all three branches are load-bearing:
- *Nothing listening* → start the server.
- *Running, source hash matches `/api/version`* → do nothing but focus. Restarting a
  healthy server on every click would be its own bug.
- *Running, hash differs* → **stale**: kill by PID from `lsof` (never by name — that
  would also kill a running `./dev.sh`) and relaunch. Without this check, a server
  started before an update stays up forever, quietly serving old code.

It focuses an existing window via `osascript` rather than `open -na`, which forces a
new browser instance and gives you one window per click. Launcher failures land in
`~/Library/Logs/SetTheory.log`, not `/dev/null`.

There is deliberately **no autostart**, for the same reason as Sessions: macOS walls
`~/Documents` off from background agents, and both the repo and the data dir live
there.

## Gotchas — each of these is a bug that actually happened

- **Units.** A label's track count and its release count are different things. The
  first version rendered "PVAS — 2 of 1", comparing tracks to releases, which is
  impossible. `owned` counts *distinct releases*; `n` counts tracks in that colour.
  A discography smaller than what's owned is stale, so `releases` is zeroed rather
  than shown as a lie. Don't reintroduce a mixed-unit ratio.
- **O'Flynn.** Label names go in the DOM as text, never into an HTML string. The
  original built `onclick="setStatus('O'Flynn')"`, whose apostrophe closed the JS
  string and silently killed every button on that card. This is why `app.js` uses
  `el()` + `addEventListener` throughout.
- **`STRUCT_RE`.** A note containing `## Something` or `**Field:**` would parse back
  as file structure — inventing a phantom label and truncating the note. The write
  is refused with a 400 and the frontend surfaces it. Failures visible, never
  silent.
- **The read-modify-write must be atomic.** `set_label()` holds `_lock` across
  parse→modify→write, not just the write. The server is threaded; clicking a status
  while a notes box blurs fires two POSTs at once, and guarding only the write lets
  the second clobber the first. Symptom: UI says "walked", file says "never".
- **`dev.sh` waits for the port to free after a kill.** The socket lingers; checking
  `lsof` in the next breath makes a restart refuse to start for no reason.
- **`.gitignore` has no trailing comments.** `.cache/  # audio` matches nothing —
  git will happily stage the user's music into a public repo. Verify with
  `git add -A -n` before any first push.

## Testing changes

No automated suite. Drive the dev API and the real DOM:

```sh
./dev.sh fresh
curl -s localhost:4398/api/state | python3 -m json.tool
curl -s -X POST localhost:4398/api/label -H 'Content-Type: application/json' \
  -d '{"name":"Test","status":"dipped","notes":"hello"}'
cat .devdata/labels.md          # the write is only real if it landed here
./dev.sh                        # restart — does it parse back identically?
```

**Frontend claims need `./devbrowser.py`, not a reading.** Each invocation is a
fresh page context, so a click and the assertion about it must be in the *same*
expression. The status-clobbering race above was invisible to curl and to the
source; one scripted click exposed it in seconds.
