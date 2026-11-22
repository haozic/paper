'use strict';
const VERSION = '20261122a';
const state = { items: [], year: '2026', query: '', visible: 40, current: -1, font: +(localStorage.getItem('speech-font') || 19) };
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
  $('articleTitle').textContent = item.t; $('articleSubtitle').textContent = item.d; $('readerDate').textContent = dateOf(item);
  $('original').href = item.u;
  $('articleBody').innerHTML = '<p>正在加载正文…</p>';
  $('previous').disabled = state.current >= state.items.length - 1;
  $('next').disabled = state.current <= 0;
  if (replace) history.replaceState(null,'','#id='+articleId(item)); else history.pushState(null,'','#id='+articleId(item));
  window.scrollTo(0,0);
  if (!item.p) { $('articleBody').innerHTML = '<p>官网原文目前无法读取，请使用下方官网链接查看。</p>'; return; }
  try {
    const response = await fetch('../' + item.p); if (!response.ok) throw Error(response.status);
    $('articleBody').innerHTML = renderBody(await response.text());
  } catch (_) { $('articleBody').innerHTML = '<p>正文加载失败，请刷新或访问官网原文。</p>'; }
}
function showLibrary() { $('reader').hidden = true; $('library').hidden = false; history.pushState(null,'','#'); window.scrollTo(0,0); }
async function init() {
  document.documentElement.style.setProperty('--reading-size',state.font+'px');
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
$('previous').onclick = () => { if (state.current < state.items.length-1) openArticle(state.items[state.current+1],true); };
$('next').onclick = () => { if (state.current > 0) openArticle(state.items[state.current-1],true); };
$('settings').onclick = () => { state.font = state.font >= 23 ? 17 : state.font+2; localStorage.setItem('speech-font',state.font); document.documentElement.style.setProperty('--reading-size',state.font+'px'); };
window.onpopstate = () => { const id=location.hash.match(/id=(ARTI\d+)/)?.[1]; const item=state.items.find(a=>articleId(a)===id); if(item) openArticle(item,true); else { $('reader').hidden=true; $('library').hidden=false; } };
init();
