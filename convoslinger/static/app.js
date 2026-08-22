/* convoslinger management app — vanilla, no build step. */

const $ = (sel) => document.querySelector(sel);
let state = { site: {}, convos: [], inbox: [], git: {}, ai: {} };
let pending = null; // {filename, content} staged for import

// On the LAN the server issues a token; it arrives as ?k= and is mirrored into
// a cookie. Send it explicitly too, so a browser that drops the cookie still works.
const TOKEN = (new URLSearchParams(location.search).get('k'))
  || (document.cookie.match(/(?:^|;\s*)convoslinger_token=([^;]+)/) || [])[1]
  || '';

async function api(path, body) {
  const headers = { 'Content-Type': 'application/json', 'X-Convoslinger': '1' };
  if (TOKEN) headers['X-Convoslinger-Token'] = TOKEN;
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

let toastTimer;
function toast(message, bad) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.toggle('bad', !!bad);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, bad ? 12000 : 5000);
}

function adopt(data) {
  if (data.site) state.site = data.site;
  if (data.convos) state.convos = data.convos;
  if (data.inbox) state.inbox = data.inbox;
  if (data.git) state.git = data.git;
  if (data.ai) state.ai = data.ai;
  render();
}

/* ---------- rendering ---------- */

function render() {
  $('#site-title').value = state.site.title || '';
  $('#site-tagline').value = state.site.tagline || '';
  $('#site-footer').value = state.site.footer || '';
  $('#site-sort').value = state.site.sort || 'date';

  const git = state.git || {};
  const dirty = (git.pending || []).length;
  $('#gitmeta').textContent =
    `${git.branch || '?'} · ${dirty ? dirty + ' file(s) to publish' : 'nothing to publish'}`;
  $('#ai-new').hidden = !(state.ai && state.ai.available);

  renderInbox();
  renderList();
}

function renderInbox() {
  const panel = $('#inbox-panel');
  const box = $('#inbox');
  panel.hidden = !state.inbox.length;
  box.textContent = '';
  state.inbox.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'inbox-item';
    const name = document.createElement('div');
    const n = document.createElement('div');
    n.className = 'name';
    n.textContent = item.file;
    const sub = document.createElement('div');
    sub.className = 'sub';
    sub.textContent = item.suggested_title;
    name.append(n, sub);
    const spacer = document.createElement('span');
    spacer.className = 'spacer';
    row.append(name, spacer);
    if (item.secrets) {
      const warn = document.createElement('span');
      warn.className = 'warn';
      warn.textContent = `${item.secrets} possible secret(s) — will be redacted`;
      row.append(warn);
    }
    const draft = document.createElement('button');
    draft.className = 'btn';
    draft.textContent = 'import hidden';
    draft.onclick = () => importInbox(item.file, false);
    const pub = document.createElement('button');
    pub.className = 'btn primary';
    pub.textContent = 'import + publish';
    pub.onclick = () => importInbox(item.file, true);
    row.append(draft, pub);
    box.append(row);
  });
}

function renderList() {
  const list = $('#list');
  list.textContent = '';
  const shown = state.convos.filter((c) => c.visible).length;
  $('#counts').textContent = `${shown} shown / ${state.convos.length} total`;

  if (!state.convos.length) {
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = 'Nothing here yet. Add a conversation above.';
    list.append(p);
    return;
  }

  state.convos.forEach((convo, index) => {
    const node = $('#row-template').content.cloneNode(true);
    const row = node.querySelector('.convo');
    row.dataset.id = convo.id;
    row.classList.toggle('hidden-row', !convo.visible);
    row.querySelector('[data-role="id"]').textContent = convo.id;
    row.querySelector('[data-field="visible"]').checked = convo.visible;
    row.querySelector('[data-field="pinned"]').checked = convo.pinned;
    row.querySelector('[data-field="title"]').value = convo.title || '';
    row.querySelector('[data-field="synopsis"]').value = convo.synopsis || '';
    row.querySelector('[data-field="date"]').value = convo.date || '';
    row.querySelector('[data-field="tags"]').value = (convo.tags || []).join(', ');

    const open = row.querySelector('[data-act="open"]');
    if (convo.visible) open.href = '/site/' + convo.path + (TOKEN ? '?k=' + encodeURIComponent(TOKEN) : '');
    else open.setAttribute('aria-disabled', 'true');

    row.querySelector('[data-field="visible"]').onchange = (e) => {
      convo.visible = e.target.checked;
      row.classList.toggle('hidden-row', !convo.visible);
    };
    row.querySelector('[data-field="pinned"]').onchange = (e) => { convo.pinned = e.target.checked; };
    row.querySelector('[data-act="up"]').onclick = () => move(index, -1);
    row.querySelector('[data-act="down"]').onclick = () => move(index, 1);
    row.querySelector('[data-act="del"]').onclick = () => remove(convo);
    const ai = row.querySelector('[data-act="ai"]');
    if (state.ai && state.ai.available) ai.onclick = () => describeRow(convo.id, row);
    else ai.setAttribute('aria-disabled', 'true');

    list.append(node);
  });
}

function collect() {
  return Array.prototype.map.call(document.querySelectorAll('.convo'), (row) => ({
    id: row.dataset.id,
    title: row.querySelector('[data-field="title"]').value,
    synopsis: row.querySelector('[data-field="synopsis"]').value,
    date: row.querySelector('[data-field="date"]').value,
    tags: row.querySelector('[data-field="tags"]').value.split(',').map((t) => t.trim()).filter(Boolean),
    visible: row.querySelector('[data-field="visible"]').checked,
    pinned: row.querySelector('[data-field="pinned"]').checked,
  }));
}

/* ---------- actions ---------- */

function move(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= state.convos.length) return;
  const edited = collect();
  [edited[index], edited[target]] = [edited[target], edited[index]];
  state.convos = edited.map((e) => Object.assign({}, state.convos.find((c) => c.id === e.id), e));
  if ((state.site.sort || 'date') !== 'manual') {
    toast('Order is set to "newest first" — switch Order to manual for this to show up on the site.');
  }
  renderList();
}

async function save() {
  const site = {
    title: $('#site-title').value,
    tagline: $('#site-tagline').value,
    footer: $('#site-footer').value,
    sort: $('#site-sort').value,
  };
  try {
    const data = await api('/api/save', { site, convos: collect() });
    adopt(data);
    toast(`Saved. Rebuilt ${data.built} page(s). Publish when you're ready.`);
  } catch (err) {
    toast(err.message, true);
  }
}

async function remove(convo) {
  if (!confirm(`Delete "${convo.title}"?\n\nThe page and the stored source are both removed. Earlier git commits still contain them.`)) return;
  try {
    adopt(await api('/api/delete', { id: convo.id }));
    toast('Deleted.');
  } catch (err) {
    toast(err.message, true);
  }
}

async function publish() {
  const message = prompt('Commit message', 'Update saved conversations');
  if (message === null) return;
  const button = $('#publish');
  button.disabled = true;
  button.textContent = 'Publishing…';
  try {
    const data = await api('/api/publish', { message });
    adopt(data);
    if (data.nothing_to_do) toast(data.log);
    else if (data.ok) toast(`Published.\n${state.git.pages_url || ''}`);
    else toast(`Publish failed:\n${data.log}`, true);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
    button.textContent = 'Publish';
  }
}

async function describeRow(id, row) {
  toast('Asking Claude…');
  try {
    const data = await api('/api/describe', { id });
    if (data.title) row.querySelector('[data-field="title"]').value = data.title;
    if (data.synopsis) row.querySelector('[data-field="synopsis"]').value = data.synopsis;
    if (data.tags && data.tags.length) row.querySelector('[data-field="tags"]').value = data.tags.join(', ');
    toast(data.truncated
      ? 'Filled in — note the transcript was long, so the middle was left out of the summary. Save to keep.'
      : 'Filled in. Save to keep.');
  } catch (err) {
    toast(err.message, true);
  }
}

function stage(filename, content) {
  pending = { filename, content };
  $('#paste').value = content.length > 4000 ? content.slice(0, 4000) + '\n… (' + content.length + ' characters loaded)' : content;
  $('#add-note').textContent = `${filename} loaded — ${content.length} characters`;
}

async function add() {
  const content = pending ? pending.content : $('#paste').value;
  if (!content.trim()) { toast('Nothing to add — drop a file or paste some text.', true); return; }
  try {
    const data = await api('/api/import', {
      filename: pending ? pending.filename : 'pasted.md',
      content,
      title: $('#new-title').value,
      date: $('#new-date').value,
      synopsis: $('#new-synopsis').value,
      tags: $('#new-tags').value.split(',').map((t) => t.trim()).filter(Boolean),
      visible: $('#new-visible').checked,
      scrub: $('#new-scrub').checked,
      thinking: $('#new-thinking').checked,
    });
    adopt(data);
    ['#paste', '#new-title', '#new-synopsis', '#new-tags'].forEach((s) => { $(s).value = ''; });
    pending = null;
    $('#add-note').textContent = '';
    const found = data.findings || [];
    toast(found.length
      ? `Added "${data.entry.title}". ${found.length} possible secret(s) were redacted — check the page before publishing.`
      : `Added "${data.entry.title}".`, found.length > 0);
  } catch (err) {
    toast(err.message, true);
  }
}

async function importInbox(file, visible) {
  try {
    const data = await api('/api/inbox-import', { file, visible });
    adopt(data);
    toast(`Imported ${file} as "${data.entry.title}".`);
  } catch (err) {
    toast(err.message, true);
  }
}

async function describeNew() {
  const content = pending ? pending.content : $('#paste').value;
  if (!content.trim()) { toast('Load a conversation first.', true); return; }
  toast('Asking Claude…');
  try {
    const data = await api('/api/describe', { content });
    if (data.title) $('#new-title').value = data.title;
    if (data.synopsis) $('#new-synopsis').value = data.synopsis;
    if (data.tags && data.tags.length) $('#new-tags').value = data.tags.join(', ');
    toast('Filled in.');
  } catch (err) {
    toast(err.message, true);
  }
}

/* ---------- wiring ---------- */

function readFile(file) {
  const reader = new FileReader();
  reader.onload = () => stage(file.name, String(reader.result || ''));
  reader.readAsText(file);
}

$('#pick').onclick = () => $('#file').click();
$('#file').onchange = (e) => { if (e.target.files[0]) readFile(e.target.files[0]); };
$('#add').onclick = add;
$('#ai-new').onclick = describeNew;
$('#save').onclick = save;
$('#publish').onclick = publish;
$('#new-date').value = new Date().toISOString().slice(0, 10);
if (TOKEN) $('#preview-site').href = '/site/index.html?k=' + encodeURIComponent(TOKEN);

const drop = $('#drop');
['dragenter', 'dragover'].forEach((type) =>
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((type) =>
  drop.addEventListener(type, () => drop.classList.remove('over')));
drop.addEventListener('drop', (e) => {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) readFile(file);
});
$('#paste').addEventListener('input', () => { pending = null; $('#add-note').textContent = ''; });

api('/api/state').then(adopt).catch((err) => toast(err.message, true));
