// carry.js — todo app over the operator-core substrate.
//
// Reads /api/items, filters to tags includes "todo", and lets you:
//   * create a new todo (PUT /api/file with sane backpack-item frontmatter)
//   * pin / unpin (POST /api/verb)
//   * mark done by demoting to hoard with aged_out_at (POST /api/verb demote)
//
// All schema defaults are aligned with backpack-item.schema.json:
//   memory_class: expiring-tactical    (TTL-managed, ages out)
//   freshness_class: current
//   source: { kind: manual, ref: carry }
//   tags: [todo, ...]
//
// Nothing is ever deleted; "done" lives forever in hoard/YYYY/MM/DD/.

const $ = (s) => document.querySelector(s);
const COMFORT_BUDGET = 8;

const State = {
  items: [],
  lastArea: localStorage.getItem('carry.area') || 'life',
  lastTtl: localStorage.getItem('carry.ttl') || '604800',
};

// ---------- API ----------

async function listItems() {
  const r = await fetch('/api/items');
  if (!r.ok) throw new Error('items: ' + r.status);
  const { items } = await r.json();
  return (items || [])
    .filter((it) => it.layer === 'backpack')
    .filter((it) => (it.tags || []).includes('todo'));
}

async function writeFile(path, body) {
  const r = await fetch('/api/file?path=' + encodeURIComponent(path), {
    method: 'PUT',
    headers: { 'Content-Type': 'text/plain' },
    body,
  });
  if (!r.ok) throw new Error('write: ' + r.status);
  return r.json();
}

async function verb(name, id) {
  const r = await fetch('/api/verb', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verb: name, id }),
  });
  return { status: r.status, body: await r.json() };
}

// ---------- helpers ----------

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/['"]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'todo';
}

function isoUtc(d = new Date()) {
  return d.toISOString().replace(/\.\d+Z$/, 'Z');
}

function todayDate(d = new Date()) {
  return d.toISOString().slice(0, 10);
}

function secondsHumanLeft(item) {
  if (!item.ttl_seconds || !item.created_at) return null;
  const created = Date.parse(item.created_at);
  if (Number.isNaN(created)) return null;
  const expires = created + item.ttl_seconds * 1000;
  const ms = expires - Date.now();
  if (ms <= 0) return { stale: true, label: 'TTL expired' };
  const days = Math.floor(ms / 86400000);
  if (days >= 1) return { stale: false, label: days + 'd left' };
  const hours = Math.floor(ms / 3600000);
  if (hours >= 1) return { stale: false, label: hours + 'h left' };
  return { stale: false, label: '<1h left' };
}

function ageHuman(item) {
  if (!item.created_at) return null;
  const created = Date.parse(item.created_at);
  if (Number.isNaN(created)) return null;
  const ms = Date.now() - created;
  if (ms < 0) return 'queued';
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return minutes + 'm old';
  const hours = Math.floor(ms / 3600000);
  if (hours < 24) return hours + 'h old';
  const days = Math.floor(ms / 86400000);
  return days + 'd old';
}

// Minimal YAML emitter for our known field shape.
// Avoids pulling in a yaml dep client-side; we control every key we write.
function yamlEmit(fm) {
  const lines = ['---'];
  const order = [
    'id', 'freshness_class', 'memory_class', 'area', 'source',
    'dated', 'created_at', 'ttl_seconds', 'tags', 'summary', 'renderer_hints',
  ];
  for (const k of order) {
    const v = fm[k];
    if (v === undefined) continue;
    lines.push(...yamlField(k, v, 0));
  }
  lines.push('---');
  return lines.join('\n') + '\n';
}

function yamlField(key, value, indent) {
  const pad = '  '.repeat(indent);
  if (Array.isArray(value)) {
    if (!value.length) return [`${pad}${key}: []`];
    return [
      `${pad}${key}:`,
      ...value.map((v) => `${pad}  - ${yamlScalar(v)}`),
    ];
  }
  if (value && typeof value === 'object') {
    const out = [`${pad}${key}:`];
    for (const [k, v] of Object.entries(value)) {
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        out.push(...yamlField(k, v, indent + 1));
      } else if (Array.isArray(v)) {
        out.push(...yamlField(k, v, indent + 1));
      } else {
        out.push(`${pad}  ${k}: ${yamlScalar(v)}`);
      }
    }
    return out;
  }
  return [`${pad}${key}: ${yamlScalar(value)}`];
}

function yamlScalar(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  const s = String(v);
  if (/^[\w\-./@:]+$/.test(s) && !/^[\d]/.test(s)) return s;
  return JSON.stringify(s);
}

function buildItemMarkdown({ summary, area, ttl, tags }) {
  const date = todayDate();
  const id = `${slugify(summary)}-${date}`;
  const fm = {
    id,
    freshness_class: 'current',
    memory_class: 'expiring-tactical',
    area,
    source: { kind: 'manual', ref: 'carry' },
    dated: date,
    created_at: isoUtc(),
    ttl_seconds: Number(ttl),
    tags: Array.from(new Set(['todo', ...tags])),
    summary,
    renderer_hints: {
      surfaces: ['session-primer', 'daily-brief', 'narrator-list', 'narrator-brief'],
      priority: 50,
    },
  };
  const body = `${date} — ${summary}\n`;
  return { id, path: `backpack/current/${id}.md`, content: yamlEmit(fm) + body };
}

// ---------- render ----------

function setStatus(text, kind = '') {
  const el = $('#status');
  el.textContent = text;
  el.classList.toggle('status-ok', kind === 'ok');
  el.classList.toggle('status-warn', kind === 'warn');
  if (kind) {
    setTimeout(() => {
      el.textContent = '';
      el.classList.remove('status-ok', 'status-warn');
    }, 2400);
  }
}

function setWeight(count) {
  const fill = $('#weight-fill');
  const num = $('#weight-num');
  const wrap = $('#weight');
  const pct = Math.min(100, (count / COMFORT_BUDGET) * 100);
  fill.style.width = pct + '%';
  num.textContent = `${count}/${COMFORT_BUDGET}`;
  wrap.classList.toggle('heavy', count > COMFORT_BUDGET);
}

function compareItems(a, b) {
  const ap = a.freshness_class === 'pinned' ? 1 : 0;
  const bp = b.freshness_class === 'pinned' ? 1 : 0;
  if (ap !== bp) return bp - ap;
  const apri = (a.priority || 0);
  const bpri = (b.priority || 0);
  if (apri !== bpri) return bpri - apri;
  // older first, so completing is satisfying as items climb
  return (a.created_at || '').localeCompare(b.created_at || '');
}

function renderList() {
  const list = $('#list');
  const empty = $('#empty');
  list.innerHTML = '';
  const sorted = State.items.slice().sort(compareItems);
  setWeight(sorted.length);
  if (!sorted.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  const tpl = $('#row-template');
  for (const item of sorted) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.id = item.id;
    if (item.freshness_class === 'pinned') node.classList.add('pinned');
    if (item.stale) node.classList.add('stale');

    node.querySelector('.title').textContent = item.summary || item.id;

    const meta = node.querySelector('.meta');
    const left = secondsHumanLeft(item);
    const parts = [];
    if (item.area) parts.push(`<span class="area">${item.area}</span>`);
    const age = ageHuman(item);
    if (age) parts.push(`<span class="age">${age}</span>`);
    if (left) parts.push(`<span class="ttl">${left.label}</span>`);
    if (item.freshness_class === 'pinned') parts.push(`<span>pinned</span>`);
    meta.innerHTML = parts.join(' <span class="dot">·</span> ');

    const checkBtn = node.querySelector('.check');
    checkBtn.addEventListener('click', () => onComplete(item, node));
    const pinBtn = node.querySelector('.pin');
    pinBtn.addEventListener('click', () => onTogglePin(item));

    list.appendChild(node);
  }
}

// ---------- actions ----------

async function refresh() {
  try {
    State.items = await listItems();
    renderList();
  } catch (e) {
    setStatus('refresh failed', 'warn');
    console.error(e);
  }
}

async function onAdd(ev) {
  ev.preventDefault();
  const input = $('#add-input');
  const summary = input.value.trim();
  if (!summary) return;
  const area = $('#add-area').value;
  const ttl = $('#add-ttl').value;
  localStorage.setItem('carry.area', area);
  localStorage.setItem('carry.ttl', ttl);

  const { id, path, content } = buildItemMarkdown({ summary, area, ttl, tags: [] });
  setStatus('saving…');
  try {
    await writeFile(path, content);
    input.value = '';
    setStatus('added', 'ok');
    await refresh();
  } catch (e) {
    setStatus('add failed', 'warn');
    console.error(e);
  }
}

async function onComplete(item, node) {
  // Optimistic: animate the row out, then call demote. If it fails, restore.
  node.classList.add('leaving');
  setStatus('moving to hoard…');
  const res = await verb('demote', item.id);
  if (res.body && res.body.ok) {
    setStatus('done — kept in hoard', 'ok');
    await refresh();
  } else {
    node.classList.remove('leaving');
    setStatus(res.body && (res.body.message || res.body.error) || 'demote failed', 'warn');
  }
}

async function onTogglePin(item) {
  const isPinned = item.freshness_class === 'pinned';
  const res = await verb(isPinned ? 'unpin' : 'pin', item.id);
  if (res.body && res.body.ok) {
    setStatus(isPinned ? 'unpinned' : 'pinned', 'ok');
    await refresh();
  } else {
    setStatus(res.body && (res.body.message || res.body.error) || 'pin failed', 'warn');
  }
}

// ---------- bootstrap ----------

function init() {
  $('#add-form').addEventListener('submit', onAdd);
  $('#add-area').value = State.lastArea;
  $('#add-ttl').value = State.lastTtl;
  refresh().then(() => setStatus(''));
}

document.addEventListener('DOMContentLoaded', init);
