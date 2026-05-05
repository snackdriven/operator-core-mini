// app.js — three-pane operator console.
//
// Owns: file tree, editor, save, renderer preview, top-bar controls.
// The command palette lives in palette.js and reads/writes State directly.

const State = {
  tree: null,
  items: [],
  currentPath: null,
  dirty: false,
  rendererId: 'session-primer',
  energy: '',
  skin: '',
  now: '',
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const RENDERERS = [
  'session-primer',
  'daily-brief',
  'statusline',
  'narrator-list',
  'narrator-brief',
];

// ---------- status helpers ----------

let statusTimer = null;
function setStatus(text, kind = '') {
  const el = $('#status');
  el.textContent = text;
  el.className = 'status' + (kind ? ' ' + kind : '');
  if (statusTimer) clearTimeout(statusTimer);
  if (kind) {
    statusTimer = setTimeout(() => {
      el.textContent = 'ready';
      el.className = 'status';
    }, 3000);
  }
}

// ---------- API ----------

const API = {
  async tree() {
    const r = await fetch('/api/tree');
    return r.json();
  },
  async items() {
    const r = await fetch('/api/items');
    return r.json();
  },
  async readFile(path) {
    const r = await fetch('/api/file?path=' + encodeURIComponent(path));
    if (!r.ok) throw new Error('read failed: ' + r.status);
    return r.text();
  },
  async writeFile(path, content) {
    const r = await fetch('/api/file?path=' + encodeURIComponent(path), {
      method: 'PUT',
      headers: { 'Content-Type': 'text/plain' },
      body: content,
    });
    return r.json();
  },
  async render(renderer, opts) {
    const r = await fetch('/api/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ renderer, ...opts }),
    });
    return r.json();
  },
  async verb(verb, id, opts = {}) {
    const r = await fetch('/api/verb', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verb, id, ...opts }),
    });
    return { status: r.status, body: await r.json() };
  },
};

// ---------- tree ----------

function renderTree() {
  const root = $('#tree-body');
  root.innerHTML = '';
  if (!State.tree) return;

  const itemByPath = new Map(State.items.map((it) => [it.path, it]));

  for (const layer of ['backpack', 'doctrine', 'hoard', 'policy']) {
    const files = State.tree.tree[layer] || [];
    if (!files.length) continue;

    const wrap = document.createElement('div');
    wrap.className = 'tree-layer';
    const head = document.createElement('div');
    head.className = 'tree-layer-name';
    head.textContent = `${layer} (${files.length})`;
    wrap.appendChild(head);

    let lastSubdir = null;
    for (const f of files) {
      if (f.subdir !== lastSubdir && f.subdir && f.subdir !== '.') {
        const sd = document.createElement('div');
        sd.className = 'tree-subdir';
        sd.textContent = f.subdir + '/';
        wrap.appendChild(sd);
        lastSubdir = f.subdir;
      }
      const row = document.createElement('div');
      row.className = 'tree-item';
      row.dataset.path = f.path;
      row.textContent = f.name;
      const meta = itemByPath.get(f.path);
      if (meta) {
        if (meta.stale) row.classList.add('stale');
        if (meta.freshness_class === 'pinned') row.classList.add('pinned');
        row.title = [
          meta.id && `id: ${meta.id}`,
          meta.freshness_class && `freshness: ${meta.freshness_class}`,
          meta.area && `area: ${meta.area}`,
          meta.dated && `dated: ${meta.dated}`,
          meta.stale && 'TTL EXPIRED',
        ].filter(Boolean).join(' · ');
      }
      if (f.path === State.currentPath) row.classList.add('active');
      row.addEventListener('click', () => loadFile(f.path));
      wrap.appendChild(row);
    }
    root.appendChild(wrap);
  }
}

// ---------- editor ----------

async function loadFile(path) {
  if (State.dirty) {
    if (!confirm('Unsaved changes. Discard?')) return;
  }
  try {
    const text = await API.readFile(path);
    State.currentPath = path;
    State.dirty = false;
    $('#editor').value = text;
    $('#editor-path').textContent = path;
    $('#save-btn').disabled = true;
    renderTree();
  } catch (e) {
    setStatus('open failed', 'warn');
    console.error(e);
  }
}

async function saveCurrent() {
  if (!State.currentPath || !State.dirty) return;
  setStatus('saving…');
  try {
    const r = await API.writeFile(State.currentPath, $('#editor').value);
    if (!r.ok) throw new Error(r.error || 'save failed');
    State.dirty = false;
    $('#save-btn').disabled = true;
    setStatus('saved', 'ok');
    // refresh derived item state + re-render the active surface
    refreshItems();
    runRender(State.rendererId);
  } catch (e) {
    setStatus('save failed', 'warn');
    console.error(e);
  }
}

// ---------- preview ----------

function renderTabs() {
  const tabs = $('#renderer-tabs');
  tabs.innerHTML = '';
  for (const r of RENDERERS) {
    const b = document.createElement('button');
    b.textContent = r;
    if (r === State.rendererId) b.classList.add('active');
    b.addEventListener('click', () => {
      State.rendererId = r;
      renderTabs();
      runRender(r);
    });
    tabs.appendChild(b);
  }
}

let renderSeq = 0;
async function runRender(rendererId) {
  const out = $('#renderer-output');
  out.classList.remove('error');
  const mySeq = ++renderSeq;
  out.textContent = `rendering ${rendererId}…`;
  try {
    const r = await API.render(rendererId, {
      now: State.now || undefined,
      energy: State.energy || undefined,
      skin: State.skin || undefined,
    });
    if (mySeq !== renderSeq) return; // stale
    if (!r.ok) {
      out.classList.add('error');
      out.textContent = r.output || '(no output)';
    } else {
      out.textContent = r.output;
    }
  } catch (e) {
    if (mySeq !== renderSeq) return;
    out.classList.add('error');
    out.textContent = String(e);
  }
}

// ---------- top-bar controls ----------

function bindControls() {
  $('#energy').addEventListener('change', (e) => {
    State.energy = e.target.value;
    runRender(State.rendererId);
  });
  $('#skin').addEventListener('change', (e) => {
    State.skin = e.target.value;
    runRender(State.rendererId);
  });
  $('#now').addEventListener('change', (e) => {
    State.now = e.target.value.trim();
    runRender(State.rendererId);
  });
  $('#rerender-btn').addEventListener('click', () => runRender(State.rendererId));
  $('#save-btn').addEventListener('click', saveCurrent);
  $('#editor').addEventListener('input', () => {
    if (!State.currentPath) return;
    State.dirty = true;
    $('#save-btn').disabled = false;
  });
  document.addEventListener('keydown', (e) => {
    const meta = e.metaKey || e.ctrlKey;
    if (meta && e.key === 's') {
      e.preventDefault();
      saveCurrent();
    }
    if (meta && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      Palette.open();
    }
  });
}

// ---------- bootstrap ----------

async function refreshTree() {
  const r = await API.tree();
  State.tree = r;
  renderTree();
}

async function refreshItems() {
  const r = await API.items();
  State.items = r.items || [];
  renderTree();
}

async function init() {
  renderTabs();
  bindControls();
  await refreshTree();
  await refreshItems();
  await runRender(State.rendererId);
  setStatus('ready');
}

window.App = {
  State,
  API,
  refreshTree,
  refreshItems,
  loadFile,
  runRender,
};

document.addEventListener('DOMContentLoaded', init);
