'use strict';
const VERSION = '20261122b';
const savedSettings = JSON.parse(localStorage.getItem('speech-reading') || '{}');
const state = { items: [], year: '2026', query: '', visible: 40, current: -1,
  reading: { font: savedSettings.font || '20', theme: savedSettings.theme || 'auto', line: savedSettings.line || '2.05', indent: savedSettings.indent || '2', paper: savedSettings.paper || 'default' } };
const $ = id => document.getElementById(id);
const articleId = item => item.p?.match(/ARTI\d+/)?.[0] || item.u.match(/ARTI\d+/)?.[0];
const safe = value => String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function dateOf(item) { const m = item.u.match(/\/(20\d\d)\/(\d\d)\/(\d\d)\//); return m ? `${m[1]}.${m[2]}.${m[3]}` : String(item.y); }
function filtered() { const q = state.query.toLocaleLowerCase('zh-CN'); return state.items.filter(a => (state.year === 'all' || String(a.y) === state.year) && (!q || (a.t + ' ' + a.d).toLocaleLowerCase('zh-CN').includes(q))); }
function renderYears() {
  const years = [...new Set(state.items.map(a => a.y))].sort((a,b) => b-a);
  $('years').replaceChildren();
  for (const y of ['all', ...years]) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = y === 'all' ? '全部' : y + '年'; b.setAttribute('aria-pressed', String(state.year === String(y)));
    b.onclick = () => { state.year = String(y); state.visible = 40; renderYears(); renderList(); };
    $('years').append(b);
  }
}
function renderList() {
  const rows = filtered();
  $('listTitle').textContent = state.query ? '搜索结果' : state.year === 'all' ? '全部讲话' : state.year + '年';
  $('resultCount').textContent = rows.length + ' 篇';
  const frag = document.createDocumentFragment();
  for (const item of rows.slice(0, state.visible)) {
    const b = document.createElement('button'); b.className = 'row'; b.type = 'button';
    const title = document.createElement('span'); title.className = 'row-title'; title.textContent = item.t;
    const subtitle = document.createElement('span'); subtitle.className = 'row-subtitle'; subtitle.textContent = item.d;
    const date = document.createElement('span'); date.className = 'row-date'; date.textContent = dateOf(item);
    b.append(title, subtitle, date); b.onclick = () => openArticle(item);
    frag.append(b);
  }
  $('list').replaceChildren(frag);
  if (!rows.length) $('list').innerHTML = '<p class="empty">没有找到相关讲话</p>';
  $('more').hidden = rows.length <= state.visible;
}
function inline(text) {
  return safe(text).replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, (_,alt,url) => `<img loading="lazy" src="${url}" alt="${alt}">`)
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function renderBody(md) {
  return md.split(/\n\s*\n/).map(block => {
    const s = block.trim(); if (!s) return '';
    const center = /^<div style="text-align:center">([\s\S]*?)<\/div>$/.exec(s);
    if (center) return '<p class="center">' + inline(center[1]) + '</p>';
    if (s.startsWith('![')) return '<p class="center">' + inline(s) + '</p>';
    return '<p>' + inline(s.replace(/^#{1,3} /,'')) + '</p>';
  }).join('');
}
async function openArticle(item, replace = false) {
  state.current = state.items.indexOf(item);
  $('library').hidden = true; $('reader').hidden = false;
  document.body.classList.add('reading');
  closePanels();
  $('articleTitle').textContent = item.t; $('articleSubtitle').textContent = item.d; $('readerDate').textContent = dateOf(item);
  $('original').href = item.u;
  $('articleBody').innerHTML = '<p>正在加载正文…</p>';
  $('next').disabled = state.current <= 0;
  renderDirectory(item);
  renderRelated();
  if (replace) history.replaceState(null,'','#id='+articleId(item)); else history.pushState(null,'','#id='+articleId(item));
  window.scrollTo(0,0);
  if (!item.p) { $('articleBody').innerHTML = '<p>官网原文目前无法读取，请使用下方官网链接查看。</p>'; return; }
  try {
    const response = await fetch('../' + item.p); if (!response.ok) throw Error(response.status);
    $('articleBody').innerHTML = renderBody(await response.text());
  } catch (_) { $('articleBody').innerHTML = '<p>正文加载失败，请刷新或访问官网原文。</p>'; }
}
function renderDirectory(item) {
  $('directoryTitle').textContent = item.y + '年 · 讲话目录';
  const list = document.createDocumentFragment();
  for (const entry of state.items.filter(a => a.y === item.y)) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = entry.t;
    if (entry === item) button.className = 'active';
    button.onclick = () => openArticle(entry, true);
    list.append(button);
  }
  $('directoryList').replaceChildren(list);
}
function renderRelated() {
  const section = $('related');
  const title = document.createElement('h2'); title.textContent = '相关阅读';
  section.replaceChildren(title);
  for (const entry of state.items.slice(state.current + 1, state.current + 4)) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = entry.t;
    const small = document.createElement('small'); small.textContent = entry.d;
    button.append(small); button.onclick = () => openArticle(entry, true);
    section.append(button);
  }
}
function closePanels() {
  $('directoryPanel').hidden = true; $('settingsPanel').hidden = true;
  $('directory').setAttribute('aria-expanded','false'); $('settings').setAttribute('aria-expanded','false');
}
function showLibrary() {
  $('reader').hidden = true; $('library').hidden = false;
  document.body.classList.remove('reading'); closePanels();
  history.pushState(null,'','#'); window.scrollTo(0,0);
}
function applySettings() {
  const r = state.reading;
  document.documentElement.style.setProperty('--reading-size',r.font+'px');
  document.documentElement.style.setProperty('--reading-line',r.line);
  document.documentElement.style.setProperty('--reading-indent',r.indent+'em');
  document.documentElement.dataset.readingPaper = r.paper;
  document.documentElement.dataset.readingTheme = r.theme === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : r.theme;
  document.querySelectorAll('[data-setting]').forEach(group => {
    group.querySelectorAll('button').forEach(b => b.classList.toggle('active',b.dataset.value === r[group.dataset.setting]));
  });
  localStorage.setItem('speech-reading',JSON.stringify(r));
}
function togglePanel(id) {
  const opening = $(id).hidden; closePanels();
  $(id).hidden = !opening;
  $(id === 'directoryPanel' ? 'directory' : 'settings').setAttribute('aria-expanded',String(opening));
}
async function init() {
  applySettings();
  try {
    const response = await fetch('../data/speeches/index.json?v='+VERSION); if (!response.ok) throw Error(response.status);
    state.items = (await response.json()).items;
    $('count').textContent = state.items.length + ' 篇 · 2012—2026';
    renderYears(); renderList();
    const id = location.hash.match(/id=(ARTI\d+)/)?.[1]; if (id) { const item = state.items.find(a => articleId(a) === id); if (item) openArticle(item,true); }
  } catch (_) { $('list').innerHTML = '<p class="empty">目录暂时无法加载，请稍后重试。</p>'; }
}
$('query').oninput = e => { state.query = e.target.value.trim(); state.year = 'all'; state.visible = 40; renderYears(); renderList(); };
$('more').onclick = () => { state.visible += 40; renderList(); };
$('back').onclick = showLibrary;
$('next').onclick = () => { if (state.current > 0) openArticle(state.items[state.current-1],true); };
$('directory').onclick = () => togglePanel('directoryPanel');
$('settings').onclick = () => togglePanel('settingsPanel');
$('toTop').onclick = () => window.scrollTo({top:0,behavior:'smooth'});
window.addEventListener('scroll',() => { $('toTop').hidden = !document.body.classList.contains('reading') || scrollY < 320; },{passive:true});
document.querySelectorAll('[data-setting]').forEach(group => group.onclick = event => {
  const button = event.target.closest('button[data-value]');
  if (!button) return;
  state.reading[group.dataset.setting] = button.dataset.value;
  applySettings();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',applySettings);
window.onpopstate = () => { const id=location.hash.match(/id=(ARTI\d+)/)?.[1]; const item=state.items.find(a=>articleId(a)===id); if(item) openArticle(item,true); else { $('reader').hidden=true; $('library').hidden=false; document.body.classList.remove('reading'); closePanels(); } };
init();
