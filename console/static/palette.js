// palette.js — ⌘K command palette.
//
// Three input shapes, all wired against window.App.State.items and the verb
// endpoints exposed by the server:
//
//   1. ">verb …"  — verbs (verify / pin / unpin / demote / render / skin / energy)
//   2. "@filter"  — filters (today, stale, aged, area:work)
//   3. "#tag"     — tag filter
//   4. anything else — fuzzy substring search across id / summary / path
//
// Selecting a row either runs the verb (verb mode) or opens the file (item mode).

const Palette = (() => {
  const overlay = () => document.getElementById('palette-overlay');
  const input = () => document.getElementById('palette-input');
  const results = () => document.getElementById('palette-results');

  let active = 0;
  let rows = [];

  // ---------- verbs ----------

  const VERBS = [
    { name: 'verify', help: 'reset created_at on <id>' },
    { name: 'pin', help: 'set freshness_class: pinned on <id>' },
    { name: 'unpin', help: 'revert freshness_class to current' },
    { name: 'demote', help: 'stamp aged_out_at and move to hoard/' },
    { name: 'render', help: 'switch active renderer in preview' },
    { name: 'skin', help: 'set narrator skin (good-place | mass-effect | "")' },
    { name: 'energy', help: 'set --energy (low-energy | high-energy | "")' },
    { name: 'now', help: 'pin --now to ISO-8601 (blank to clear)' },
  ];

  const RENDERERS = [
    'session-primer',
    'daily-brief',
    'statusline',
    'narrator-list',
    'narrator-brief',
  ];

  const SKINS = ['good-place', 'mass-effect', ''];
  const ENERGIES = ['low-energy', 'high-energy', ''];

  // ---------- filtering ----------

  function filterItems(items, query) {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => {
      const hay = [
        it.id,
        it.summary,
        it.path,
        it.area,
        it.freshness_class,
        (it.tags || []).join(' '),
      ].join(' ').toLowerCase();
      return q.split(/\s+/).every((tok) => hay.includes(tok));
    });
  }

  function applyAtFilter(items, token) {
    const t = token.toLowerCase();
    if (t === '@today') {
      const today = new Date().toISOString().slice(0, 10);
      return items.filter((it) => it.dated === today);
    }
    if (t === '@stale') return items.filter((it) => it.stale);
    if (t === '@aged') return items.filter((it) => it.layer === 'hoard');
    if (t === '@pinned') return items.filter((it) => it.freshness_class === 'pinned');
    if (t.startsWith('@area:')) {
      const a = t.slice('@area:'.length);
      return items.filter((it) => (it.area || '').toLowerCase() === a);
    }
    return items;
  }

  function applyHashFilter(items, token) {
    const tag = token.slice(1).toLowerCase();
    if (!tag) return items;
    return items.filter((it) => (it.tags || []).map((s) => s.toLowerCase()).includes(tag));
  }

  // ---------- result generation ----------

  function buildRows(query) {
    const items = (window.App && window.App.State.items) || [];

    // Verb mode.
    if (query.startsWith('>')) {
      const tail = query.slice(1).trimStart();
      const [verb, ...rest] = tail.split(/\s+/);
      const arg = rest.join(' ').trim();

      // Verb name not yet completed — list verbs.
      if (!verb || !VERBS.find((v) => v.name === verb)) {
        return VERBS
          .filter((v) => !verb || v.name.startsWith(verb))
          .map((v) => ({
            label: '>' + v.name,
            meta: v.help,
            action: () => {
              input().value = '>' + v.name + ' ';
              update();
            },
          }));
      }

      // Verbs that take an enum arg.
      if (verb === 'render') {
        return RENDERERS.filter((r) => !arg || r.includes(arg)).map((r) => ({
          label: '>render ' + r,
          meta: 'set preview to ' + r,
          action: () => {
            window.App.State.rendererId = r;
            close();
            // re-render tabs by triggering a click via event
            document.querySelectorAll('#renderer-tabs button').forEach((b) => {
              if (b.textContent === r) b.click();
            });
          },
        }));
      }
      if (verb === 'skin') {
        return SKINS.filter((s) => !arg || s.includes(arg)).map((s) => ({
          label: '>skin ' + (s || '(default)'),
          meta: 'set narrator skin',
          action: () => {
            document.getElementById('skin').value = s;
            window.App.State.skin = s;
            window.App.runRender(window.App.State.rendererId);
            close();
          },
        }));
      }
      if (verb === 'energy') {
        return ENERGIES.filter((s) => !arg || s.includes(arg)).map((s) => ({
          label: '>energy ' + (s || '(default)'),
          meta: 'set routing-rule energy',
          action: () => {
            document.getElementById('energy').value = s;
            window.App.State.energy = s;
            window.App.runRender(window.App.State.rendererId);
            close();
          },
        }));
      }
      if (verb === 'now') {
        return [{
          label: '>now ' + (arg || '(clear)'),
          meta: arg ? 'pin --now' : 'clear pinned --now',
          action: () => {
            document.getElementById('now').value = arg;
            window.App.State.now = arg;
            window.App.runRender(window.App.State.rendererId);
            close();
          },
        }];
      }

      // Verbs that take an item id.
      const matches = filterItems(items, arg).slice(0, 30);
      return matches.map((it) => ({
        label: '>' + verb + ' ' + (it.id || it.path),
        meta: [it.layer, it.freshness_class, it.summary].filter(Boolean).join(' · '),
        stale: it.stale,
        pinned: it.freshness_class === 'pinned',
        action: () => runVerb(verb, it),
      }));
    }

    // @filter and #tag composition.
    let filtered = items;
    let textPart = query.trim();
    const tokens = query.split(/\s+/);
    for (const t of tokens) {
      if (t.startsWith('@')) {
        filtered = applyAtFilter(filtered, t);
        textPart = textPart.replace(t, '').trim();
      } else if (t.startsWith('#')) {
        filtered = applyHashFilter(filtered, t);
        textPart = textPart.replace(t, '').trim();
      }
    }
    filtered = filterItems(filtered, textPart);

    return filtered.slice(0, 60).map((it) => ({
      label: it.id || it.path,
      meta: [it.layer, it.freshness_class, it.area, it.summary].filter(Boolean).join(' · '),
      stale: it.stale,
      pinned: it.freshness_class === 'pinned',
      action: () => {
        close();
        window.App.loadFile(it.path);
      },
    }));
  }

  async function runVerb(verb, item) {
    if (!item.id) {
      alert('item has no id; cannot run verb');
      return;
    }
    if (verb === 'demote' && !confirm(`demote ${item.id} → hoard/?`)) return;
    const opts = window.App.State.now ? { now: window.App.State.now } : {};
    const res = await window.App.API.verb(verb, item.id, opts);
    close();
    const status = document.getElementById('status');
    if (res.body && res.body.ok) {
      status.textContent = res.body.message || (verb + ' ok');
      status.className = 'status ok';
    } else {
      status.textContent = (res.body && (res.body.message || res.body.error)) || (verb + ' failed');
      status.className = 'status warn';
    }
    setTimeout(() => { status.textContent = 'ready'; status.className = 'status'; }, 3000);
    await window.App.refreshTree();
    await window.App.refreshItems();
    await window.App.runRender(window.App.State.rendererId);
  }

  // ---------- DOM ----------

  function update() {
    const q = input().value;
    rows = buildRows(q);
    active = 0;
    paint();
  }

  function paint() {
    const r = results();
    r.innerHTML = '';
    rows.forEach((row, i) => {
      const div = document.createElement('div');
      div.className = 'palette-row' + (i === active ? ' active' : '');
      const left = document.createElement('span');
      left.textContent = row.label;
      if (row.stale) left.classList.add('stale');
      if (row.pinned) left.classList.add('pinned');
      const right = document.createElement('span');
      right.className = 'meta';
      right.textContent = row.meta || '';
      div.appendChild(left);
      div.appendChild(right);
      div.addEventListener('click', () => row.action && row.action());
      r.appendChild(div);
    });
  }

  function move(delta) {
    if (!rows.length) return;
    active = (active + delta + rows.length) % rows.length;
    paint();
    const el = results().children[active];
    if (el) el.scrollIntoView({ block: 'nearest' });
  }

  function open() {
    overlay().hidden = false;
    input().value = '';
    update();
    setTimeout(() => input().focus(), 0);
  }

  function close() {
    overlay().hidden = true;
  }

  function bind() {
    overlay().addEventListener('click', (e) => {
      if (e.target === overlay()) close();
    });
    input().addEventListener('input', update);
    input().addEventListener('keydown', (e) => {
      if (e.key === 'Escape') return close();
      if (e.key === 'ArrowDown') { e.preventDefault(); return move(1); }
      if (e.key === 'ArrowUp') { e.preventDefault(); return move(-1); }
      if (e.key === 'Enter') {
        e.preventDefault();
        const row = rows[active];
        if (row && row.action) row.action();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', bind);

  return { open, close };
})();

window.Palette = Palette;
