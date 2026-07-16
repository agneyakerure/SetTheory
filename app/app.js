// SetTheory — vanilla, no build step, no framework.
//
// Rendering rule (same as Sessions, and it isn't cosmetic): user and Bandcamp
// data reaches the DOM through textContent only, never innerHTML and never an
// HTML string. The first version of this app built onclick="..." strings with
// label names in them, and a label called O'Flynn silently broke every button on
// its own card. Build nodes; attach listeners. Then names can contain anything.

const BLURB = {
  Green: "fun and light",
  Red: "energetic — peak time",
  Blue: "deep, meditative, everything else",
};

let D = null;      // the derived map (tracks, labels)
let SAVED = {};    // labels.md, keyed by name
let view = null;   // null = picker, otherwise a colour
let playing = null;

const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}

async function api(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  // A refused write must be loud. Silently swallowing it would leave the note
  // on screen and absent from labels.md — the worst of both.
  if (!r.ok) throw new Error(data.error || `${path} -> ${r.status}`);
  return data;
}

async function boot() {
  const s = await api("/api/state");
  D = s;
  SAVED = s.saved || {};
  $("back").addEventListener("click", () => go(null));
  $("add").addEventListener("click", addLabel);
  $("audio").addEventListener("ended", () => { playing = null; renderZone(); });
  render();
}

function rec(name) {
  return SAVED[name] || { status: "never", colors: [], url: null, notes: "", added: false };
}

async function save(name, patch) {
  try {
    SAVED[name] = await api("/api/label", { name, ...patch });
    return true;
  } catch (e) {
    alert("Couldn't save.\n\n" + e.message);
    return false;
  }
}

// Labels in a colour: derived from the map, plus hand-added ones from labels.md.
function labelsFor(color) {
  const out = D.labels
    .filter((l) => l.colors[color])
    .map((l) => ({ ...l, n: l.colors[color] }));
  for (const [name, r] of Object.entries(SAVED)) {
    if (r.added && (r.colors || []).includes(color) && !out.some((x) => x.name === name)) {
      out.push({ name, url: r.url, via: null, colors: {}, tracks: [], releases: 0, owned: 0, n: 0 });
    }
  }
  return out.sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
}

function render() {
  const picker = !view;
  $("choose").hidden = !picker;
  $("zone").hidden = picker;
  document.getElementById("app").dataset.color = view || "";
  picker ? renderPicker() : renderZone();
  window.scrollTo(0, 0);
}

function renderPicker() {
  $("choose-meta").textContent =
    `${D.tracks.length} tracks · ${D.labels.length} labels · built ${D.built || "—"}`;
  const wrap = $("picker");
  wrap.replaceChildren();
  for (const c of D.colors) {
    const b = el("button", "pick");
    b.dataset.c = c;
    b.append(el("div", "dot"), el("h2", null, c), el("p", null, BLURB[c] || ""));
    const n = D.tracks.filter((t) => t.color === c).length;
    b.append(el("div", "n", `${n} tracks · ${labelsFor(c).length} labels`));
    b.addEventListener("click", () => go(c));
    wrap.append(b);
  }
}

function renderZone() {
  const c = view;
  const mine = D.tracks.filter((t) => t.color === c);
  const labs = labelsFor(c);
  $("zone-meta").textContent = D.built || "";
  $("zone-name").textContent = c;
  $("zone-sub").textContent =
    `${BLURB[c] || ""} · ${mine.length} tracks you own · ${labs.length} labels live here`;
  $("lab-count").textContent = String(labs.length);

  const cells = $("cells");
  cells.replaceChildren();
  for (const e of D.energy) {
    const ts = mine.filter((t) => t.energy === e);
    const cell = el("div", ts.length ? "cell" : "cell empty");
    const head = el("div", "cellh");
    head.append(el("span", "tag", e), el("span", "c", ts.length ? String(ts.length) : "—"));
    const notes = [...new Set(ts.map((t) => t.note).filter(Boolean))];
    if (notes.length) head.append(el("span", "c", "· " + notes.join(", ")));
    cell.append(head);

    if (!ts.length) {
      // The gap is the information. Say why it's empty rather than hiding it.
      const fast = e.startsWith("+");
      cell.append(el("div", "why",
        `nothing here — your ${c.toLowerCase()} music doesn't go this ${fast ? "fast" : "dark"}`));
    }
    for (const t of ts) cell.append(trackRow(t));
    cells.append(cell);
  }

  const list = $("labels");
  list.replaceChildren();
  if (!labs.length) {
    list.append(el("div", "empty-note", "No labels here yet. Add one you want to explore."));
  }
  for (const l of labs) list.append(labelCard(l));
}

function trackRow(t) {
  const row = el("div", "trk" + (playing === t.id ? " on" : "") + (t.exists ? "" : " miss"));
  row.append(el("span", "play", playing === t.id ? "▮▮" : "▶"));

  const ti = el("div", "ti");
  const title = el("div", "t", t.title || "untitled file");
  if (!t.title) title.classList.add("untitled");
  ti.append(title, el("div", "a", (t.artist || "unknown") + (t.label ? " · " + t.label : "")));
  row.append(ti);

  const bits = [];
  if (t.bpm) bits.push(String(Math.round(t.bpm)));
  if (t.key) bits.push(t.key);
  row.append(el("span", "st", bits.join(" · ")));

  if (t.bc_url) {
    const a = el("a", "bc", "BC");
    a.href = t.bc_url;
    a.target = "_blank";
    a.rel = "noreferrer";
    a.addEventListener("click", (ev) => ev.stopPropagation());
    row.append(a);
  }
  row.addEventListener("click", () => play(t));
  return row;
}

function labelCard(l) {
  const r = rec(l.name);
  const card = el("div", "lab");

  const top = el("div", "lr");
  const href = r.url || l.url || l.via;
  if (href) {
    const a = el("a", "lname", l.name + " ↗");
    a.href = href;
    a.target = "_blank";
    a.rel = "noreferrer";
    top.append(a);
  } else {
    top.append(el("span", "lname", l.name));
  }

  const chips = el("div", "chips");
  for (const k of Object.keys(l.colors)) {
    const ch = el("span", "chip");
    ch.dataset.c = k;
    chips.append(ch);
  }
  top.append(chips);

  // Honest units: tracks are tracks, releases are releases. Never compare them.
  const bits = [];
  if (l.n) bits.push(`${l.n} track${l.n > 1 ? "s" : ""}`);
  if (l.releases) bits.push(`${l.owned} of ${l.releases} releases`);
  top.append(el("span", "cov", bits.join(" · ") || "not started"));
  card.append(top);

  const st = el("div", "status");
  for (const [k, label] of [["never", "never"], ["dipped", "dipped in"], ["walked", "walked it"]]) {
    const b = el("button", "sb" + (r.status === k ? " sel" : ""), label);
    b.addEventListener("click", async () => { await save(l.name, { status: k }); renderZone(); });
    st.append(b);
  }
  card.append(st);

  const nt = el("textarea", "nt");
  nt.placeholder = "notes — what does this label sound like? where were you going next?";
  nt.value = r.notes || "";
  nt.addEventListener("blur", async () => {
    if (nt.value === rec(l.name).notes) return;
    await save(l.name, { notes: nt.value });
  });
  card.append(nt);
  return card;
}

async function addLabel() {
  const name = prompt("Label name?");
  if (!name || !name.trim()) return;
  const url = prompt("Bandcamp URL? (optional)") || null;
  const r = rec(name.trim());
  const colors = [...new Set([...(r.colors || []), view])];
  await save(name.trim(), { colors, url, added: true, status: r.status || "never" });
  renderZone();
}

function go(c) {
  view = c;
  render();
}

function play(t) {
  if (!t.exists) {
    alert("That file is no longer on disk.");
    return;
  }
  playing = t.id;
  $("player").hidden = false;
  $("now-title").textContent = t.title || "untitled";
  $("now-artist").textContent = (t.artist || "unknown") + (t.label ? " · " + t.label : "");
  const au = $("audio");
  au.src = "/audio?id=" + t.id;
  au.play().catch(() => {});
  renderZone();
}

boot();
