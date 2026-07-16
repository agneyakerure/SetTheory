# Ideas & roadmap

A running backlog of things to maybe build, and — more importantly — the
*reasoning* behind what was decided, so it isn't re-argued from scratch. Not
commitments. Edit freely; delete when they stop mattering.

Three documents, one job each, same convention as Sessions. `CLAUDE.md` is **what
is** (how it works, and the principles the code rests on). `README.md` carries the
**why** for a reader. This file is **what might be** — only the undecided, plus the
measurements that constrain it.

> **The graduation rule.** When an idea ships, its reasoning moves into `CLAUDE.md`
> and *leaves this file*; the entry collapses to a one-line "Done" bullet. Built
> principles live in exactly one place, or the same argument sits in two files and
> they drift.

## What the data actually says (do not re-litigate this)

Measured from the user's Bandcamp collection (~559 purchases) and Rekordbox export
in July 2026. Every one of these was a surprise, and each one killed a design that
looked obvious beforehand:

- **His exploration is flat.** ~500 purchases across ~400 distinct Bandcamp pages;
  **83% are pages he bought from exactly once.** Deepest node in two years: Skee
  Mask, 6 releases. Only 68 of 500 purchases come from a page he returned to 3+
  times.
- **So the fog-of-war map reflects a behaviour he doesn't have yet.** There is no
  "half-walked label" in this data to draw. **He knows, and chose it anyway** — he
  wants to *become* someone who walks a catalogue end to end. The map being sparse
  is the design, not a bug. Don't "fix" it by padding it, and don't reopen the
  decision; it was made with these numbers in hand.
- **His digging is bursty, not absent.** 85 purchases in May 2025, 86 in October, 42
  in March 2026 — with months of 1–3 between. He describes never reaching flow while
  digging; the data says he regularly buys 85 records in a month. The felt problem
  and the measured behaviour disagree, which is worth remembering before believing
  any premise (including his) without checking.
- **The real bottleneck may be processing, not finding.** 500 releases bought → 140
  tracks ever judged into the grid. If this tool doesn't help, that gap is the
  likelier place to aim next.

## Deferred: fans

Half of the original ask, and not built. He follows 45 fans, and their collections
are the highest-signal object on Bandcamp — a real person's taste, filtered by
having spent money. But **nothing maps a fan to a colour** without pulling all 45
collections and matching them against his zones. That's a scraping job of its own,
on an undocumented API, for a payoff we can't estimate. Left until the label half
proves it earns attention.

## Deferred: the Sessions merge

Full argument is parked in `Sessions/IDEAS.md` — read it there rather than
duplicating it. The short version:

- **`Digging` is already a standing project in Sessions**, with its own reflection
  prompt ("What did you take home?"). This tool is upstream of that: it's what a dig
  *starts* from. Sessions owns the session; this owns the map.
- **The map half is Sessions-shaped** — derived, never maintained, a mirror. The
  architecture here was deliberately built to match so a merge is a decision, not a
  rewrite.
- **The notes half should dissolve, not port.** A label is gear-shaped. A `## Labels`
  shelf in Sessions' `studio.md` plus writing `@incienso` in a dig note gets presence
  tracking free from `studio_index()` — "showed up in 4 sessions, last seen Jul 12".
  **No new code, no form.** Sessions rejected tagging UIs outright ("Mentions, not
  forms"), and the never/dipped/walked buttons here are exactly that. If this
  graduates, they die.
- **Blocker if it ever merges:** this repo's code uses `str | None` annotations and
  resolves `python3` (3.12 here). Sessions pins `/usr/bin/python3`, which is **3.9**
  and cannot parse that syntax. Five-minute fix, but a real one.

## Smaller things

- **Coverage denominators are missing on 14 of 65 labels** — `band_details` didn't
  return a discography for them, so the card falls back to a bare track count. Not
  wrong, just thinner.
- **~31% of the 140 tracks don't match a Bandcamp purchase**, and the misses are
  almost entirely files with blank artist/title tags rather than join failures.
  Fixing the tags fixes the join; no code change would.
- **The colour scheme is hardcoded** in three places (`COLORS`/`ENERGY` in
  `build.py`, `BLURB` in `app/app.js`, the accents in `app/style.css`). Fine for one
  user; a real generalization would need one source.
- **Rebuilds are manual.** `build.py` after every Rekordbox export. A watcher would
  be easy and is probably the wrong instinct — it'd make the tool a background
  process, which is the thing Sessions refuses.

## Done

- The map: colour → your tracks by energy band → the labels that colour lives on,
  with coverage. Reasoning in `CLAUDE.md`.
- Markdown storage at `~/Documents/SetTheory/labels.md`; Sessions-shaped
  architecture, dev tooling, and Dock launcher.
