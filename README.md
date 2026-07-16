# SetTheory

A DJ set is made out of sets. This maps yours, and gives you somewhere to start
when you dig.

Open it and it asks one question: **what are you feeling?** Pick a color, and you
get the tracks you already own in that mood — playable, grouped by energy — next
to the labels that mood actually lives on, each one a door into Bandcamp. Walk
one, mark it, write down what it sounded like. Next time you're in that mood,
your notes are waiting.

## Why it exists

Digging goes wrong in a specific way: you open Bandcamp with the goal "find good
music," which is unfalsifiable and infinite, and you bounce between unrelated
albums until you're tired. There's no brief, no thread, and no memory — so every
session starts cold and you re-tread ground you covered in March.

This fixes the cold start, and only that. It doesn't find music for you.

- **Start from a mood, not a gap.** A missing cell is a chore list; nobody reaches
  flow restocking a pantry. Your mood isn't an adjective you can introspect —
  it's a record you can't stop playing. So the tool starts from what you already
  have and love, and the labels follow from it.
- **The empty cells are real.** If your blue music doesn't go past 130bpm, that
  cell renders empty and says so. Absence is invisible in a list view; it's only
  visible on a grid. That's the one thing this does that Rekordbox structurally
  cannot.
- **It shows, it doesn't prescribe.** A gap isn't automatically a need — you might
  own four tracks in a cell because you don't *want* more. The tool never tells
  you to fill anything.
- **No AI.** Nothing here generates, suggests, ranks, or recommends. Every
  judgment in it is one you made.

## The three sources

Rekordbox knows your taste but not your labels. Bandcamp knows the labels but not
your taste. The whole trick is joining them.

| source | gives |
|---|---|
| Rekordbox XML export | BPM, key, artist, album |
| `*.m3u8` cell playlists | which color + energy each track is |
| Your Bandcamp collection | the label, the release page, the catalogue size |

Two things make it work, neither of them obvious:

- **Rekordbox's `Label` field is nearly useless** — in the library this was built
  against, 13 of 140 tracks had one. Labels come from Bandcamp instead, matched
  on normalized artist + album (~69% hit rate; the misses are almost all files
  with blank tags, not join failures).
- **Bandcamp's `selling_band_id` is the label** when it differs from `band_id`.
  That's what turns five unrelated artist pages back into one label. Resolving it
  also yields the label's full discography — which is the denominator that lets a
  card say **"1 of 28 releases"** instead of just "1 track."

That denominator is the point. It's the difference between "I like this label"
and "I have walked four percent of it."

## The colors

The scheme this was built around:

- **Green** — fun and light
- **Red** — energetic, peak time
- **Blue** — deep, meditative, everything else
- **`+` / `-`** — positive / negative, with the count as the tempo band
  (`+` under 130, `++` 130–140, `+++` 140+, `++++` above)

Yours will differ. The colors and bands live at the top of `build.py`
(`COLORS`, `ENERGY`) and the descriptions in `app.html` (`BLURB`); the playlist
filenames just need to read `<Color> <energy>.m3u8`. Nothing else assumes them.

## Setup

Needs **Python 3** and **ffmpeg** (only if your library is AIFF — browsers won't
play it, so it gets transcoded and cached).

```sh
brew install ffmpeg    # skip if you're all-MP3

# In Rekordbox: File > Export Collection in xml format  -> ~/Desktop/rbcollection.xml
# Export your cell playlists as m3u8 to a folder        -> ~/Desktop/Rekordbox exports

python3 build.py https://bandcamp.com/YOURNAME
python3 server.py
```

Then open **http://localhost:8420**.

The first build resolves every label against Bandcamp and takes a few minutes;
it's cached, so re-runs are seconds. Re-run `build.py` after a fresh Rekordbox
export. The first `server.py` run warms the audio cache in the background.

Paths are configurable:

```sh
SETTHEORY_XML=~/path/to/collection.xml \
SETTHEORY_CELLS=~/path/to/playlists \
SETTHEORY_FAN=https://bandcamp.com/YOURNAME python3 build.py
```

## Your data

Stays yours, and stays out of this repo. `data.json` is derived and rebuildable.
`state.json` is your notes. `.cache/` holds your collection and your transcoded
audio. All are gitignored.

`build.py` is the only thing that touches the network, and only Bandcamp.

## Honest limits

- **The Bandcamp API is undocumented.** `api/fancollection`, `api/mobile/24` and
  the `data-blob` on your fan page are not public contracts. This will break one
  day, without warning, and that's a reason to keep it out of anything you rely
  on daily.
- **The map is only as deep as your buying.** If you buy one record from four
  hundred pages, coverage will be one-of-many everywhere, and it'll say so. That's
  the map working, not failing — but it's an uncomfortable read at first.
- **Fans aren't in here.** Nothing maps the people you follow to a color without
  scraping all their collections. Deferred, not forgotten.
- **It's built around one person's taxonomy.** See "The colors."
