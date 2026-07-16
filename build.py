#!/usr/bin/env python3
"""
SetTheory — build the map.

Joins three sources into data.json:
  1. A Rekordbox collection XML export      (track metadata: BPM, key, artist)
  2. A folder of m3u8 cell playlists         (which color/energy each track is in)
  3. Your Bandcamp collection                (the labels — Rekordbox rarely has them)

Configure with env vars, or edit the defaults:
  SETTHEORY_XML    path to the Rekordbox XML export
  SETTHEORY_CELLS  folder of "<Color> <energy>.m3u8" playlists
  SETTHEORY_FAN    your Bandcamp fan page URL

Network calls are cached in .cache/ — the first run is slow, re-runs are instant.
"""
import json, re, os, glob, urllib.parse, unicodedata, subprocess, time, html, sys
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

HERE  = os.path.dirname(os.path.abspath(__file__))
XML   = os.path.expanduser(os.environ.get('SETTHEORY_XML',   '~/Desktop/rbcollection.xml'))
CELLS = os.path.expanduser(os.environ.get('SETTHEORY_CELLS', '~/Desktop/Rekordbox exports'))
FAN   = os.environ.get('SETTHEORY_FAN', '')
CACHE = os.path.join(HERE, '.cache')
os.makedirs(CACHE, exist_ok=True)

COLORS = ['Green', 'Red', 'Blue']
ENERGY = ['++++', '+++', '++', '+', '-', '--', '---', '----']

def norm(s):
    s = unicodedata.normalize('NFKD', (s or '').lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\((original mix|original|extended mix|feat[^)]*)\)', ' ', s)
    s = re.sub(r'\b(feat|ft|featuring|remix|edit|vs|and|the)\b', ' ', s)
    return re.sub(r'[^a-z0-9]+', '', s)

def artists(s):
    return {norm(p) for p in re.split(r'[,&/]| feat | ft | x | vs ', (s or '').lower()) if norm(p)}

def curl(url, data=None):
    cmd = ['curl', '-s', '-A', 'Mozilla/5.0', url]
    if data: cmd += ['-X', 'POST', '-H', 'Content-Type: application/json', '-d', data]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout

def cell_key(name):
    """'Red ++ BUFO' -> ('Red','++','BUFO')"""
    parts = name.split()
    color = parts[0]
    energy, note = None, ''
    for p in parts[1:]:
        if set(p) <= {'+', '-'} and p: energy = p
        else: note = (note + ' ' + p).strip()
    return color, energy or '+', note

# ---------- Bandcamp ----------
def bandcamp(fan_url):
    p = os.path.join(CACHE, 'bc.json')
    if os.path.exists(p): return json.load(open(p))
    print('fetching bandcamp collection...')
    raw = curl(fan_url)
    blob = json.loads(html.unescape(re.search(r'id="pagedata"[^>]*data-blob="([^"]*)"', raw).group(1)))
    fan_id = blob['fan_data']['fan_id']
    items = {i['item_id']: i for i in blob['item_cache']['collection'].values()}
    token = blob['collection_data']['last_token']
    for _ in range(30):
        d = json.loads(curl('https://bandcamp.com/api/fancollection/1/collection_items',
                            json.dumps({"fan_id": fan_id, "older_than_token": token, "count": 100})))
        new = [i for i in d.get('items', []) if i['item_id'] not in items]
        for i in new: items[i['item_id']] = i
        if not d.get('more_available') or not new: break
        token = d.get('last_token') or token
        time.sleep(0.5)
    out = list(items.values())
    json.dump(out, open(p, 'w'))
    print(f'  {len(out)} purchases')
    return out

def bands(ids):
    """Resolve band_ids -> {name, url, releases}. Covers both labels (selling_band_id)
       and self-released artist pages (band_id). Cached; safe to re-run."""
    p = os.path.join(CACHE, 'sellers.json')
    known = json.load(open(p)) if os.path.exists(p) else {}
    todo = [i for i in ids if str(i) not in known]
    if todo: print(f'resolving {len(todo)} labels...')
    for n, sid in enumerate(todo):
        try:
            d = json.loads(curl(f'https://bandcamp.com/api/mobile/24/band_details?band_id={sid}'))
            known[str(sid)] = {'name': d.get('name'), 'url': d.get('bandcamp_url'),
                               'releases': len(d.get('discography') or [])}
        except Exception:
            known[str(sid)] = {'name': None, 'url': None, 'releases': 0}
        if n % 20 == 0:
            print(f'  {n}/{len(todo)}'); json.dump(known, open(p, 'w'))
        time.sleep(0.2)
    if todo: json.dump(known, open(p, 'w'))
    return known

# ---------- main ----------
def main(fan_url=None):
    fan_url = fan_url or FAN
    if not fan_url:
        raise SystemExit('Need your Bandcamp fan page. Either:\n'
                         '  python3 build.py https://bandcamp.com/YOURNAME\n'
                         '  SETTHEORY_FAN=https://bandcamp.com/YOURNAME python3 build.py')
    for p, what in ((XML, 'Rekordbox XML export'), (CELLS, 'cell playlist folder')):
        if not os.path.exists(p):
            raise SystemExit(f'{what} not found: {p}\n(set SETTHEORY_XML / SETTHEORY_CELLS)')
    coll = bandcamp(fan_url)
    sids = {(i.get('player_data') or {}).get('selling_band_id') for i in coll}
    sids |= {i.get('band_id') for i in coll}          # self-released pages need counts too
    sids = {s for s in sids if s}
    smap = bands(sids)

    idx = defaultdict(list)
    for i in coll:
        for a in artists(i['band_name']): idx[a].append(i)
        for a in artists((i.get('player_data') or {}).get('artist_name', '')): idx[a].append(i)

    rb = ET.parse(XML).getroot().find('COLLECTION').findall('TRACK')
    by_path = {os.path.normpath(re.sub(r'^file://localhost', '', urllib.parse.unquote(t.get('Location') or ''))): t
               for t in rb}

    tracks, labels = [], defaultdict(lambda: {'colors': Counter(), 'tracks': [], 'url': None,
                                              'via': None, 'releases': 0, 'owned': set()})
    for f in sorted(glob.glob(os.path.join(CELLS, '*.m3u8'))):
        color, energy, note = cell_key(os.path.basename(f)[:-5].strip())
        for line in open(f, encoding='utf-8', errors='replace'):
            line = line.strip()
            if not line or line.startswith('#'): continue
            p = os.path.normpath(line)
            t = by_path.get(p)
            if t is None: continue
            cands = [c for a in artists(t.get('Artist')) for c in idx.get(a, [])]
            best = None
            if cands:
                alb = norm(t.get('Album'))
                best = next((c for c in cands if alb and norm(c['item_title']) == alb), cands[0])

            lab = lab_url = None; lab_rel = 0
            if best:
                pd = best.get('player_data') or {}
                sb = pd.get('selling_band_id')
                if sb and sb != best.get('band_id') and smap.get(str(sb), {}).get('name'):
                    s = smap[str(sb)]
                    lab, lab_url, lab_rel = s['name'], s.get('url'), s.get('releases') or 0
                else:
                    lab = best['band_name']
                    b = smap.get(str(best.get('band_id'))) or {}
                    h = best.get('url_hints') or {}
                    lab_url = b.get('url') or (f"https://{h.get('subdomain')}.bandcamp.com"
                                               if h.get('subdomain') else None)
                    lab_rel = b.get('releases') or 0

            tid = len(tracks)
            tracks.append({
                'id': tid, 'path': p, 'exists': os.path.exists(p),
                'artist': (t.get('Artist') or '').strip(), 'title': (t.get('Name') or '').strip(),
                'album': (t.get('Album') or '').strip(),
                'bpm': t.get('AverageBpm'), 'key': t.get('Tonality'), 'year': t.get('Year'),
                'color': color, 'energy': energy, 'note': note,
                'label': lab, 'label_url': lab_url,
                'bc_url': best['item_url'] if best else None,
            })
            if lab:
                L = labels[lab]
                L['colors'][color] += 1
                L['tracks'].append(tid)
                L['url'] = L['url'] or lab_url
                L['releases'] = max(L['releases'], lab_rel)
                L['owned'].add(best['item_id'])          # distinct releases, not tracks
                L['via'] = L['via'] or (best['item_url'] if best else None)

    lab_out = []
    for name, L in labels.items():
        owned = len(L['owned'])
        # a discography count smaller than what we own is stale/wrong — don't show a lie
        rel = L['releases'] if L['releases'] >= owned else 0
        lab_out.append({'name': name, 'url': L['url'], 'via': L['via'],
                        'colors': dict(L['colors']), 'tracks': L['tracks'],
                        'releases': rel, 'owned': owned,
                        'total': sum(L['colors'].values()), 'source': 'derived'})
    lab_out.sort(key=lambda x: -x['total'])

    data = {'colors': COLORS, 'energy': ENERGY, 'tracks': tracks, 'labels': lab_out,
            'built': time.strftime('%Y-%m-%d %H:%M')}
    json.dump(data, open(os.path.join(HERE, 'data.json'), 'w'), indent=1)
    m = sum(1 for t in tracks if t['bc_url'])
    print(f"\n{len(tracks)} tracks | {m} matched to Bandcamp | {len(lab_out)} labels")
    for c in COLORS:
        print(f"  {c:6} {sum(1 for t in tracks if t['color']==c):3} tracks, "
              f"{sum(1 for l in lab_out if c in l['colors']):3} labels")

if __name__ == '__main__':
    main(*sys.argv[1:])
