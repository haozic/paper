'use strict';
const VERSION = '20261122c';
const savedSettings = JSON.parse(localStorage.getItem('speech-reading') || '{}');
const state = { items: [], year: 'all', query: '', visible: 40, current: -1,
  reading: { font: savedSettings.font || '20', theme: savedSettings.theme || 'auto', line: savedSettings.line || '2.05', indent: savedSettings.indent || '2', paper: savedSettings.paper || 'default' } };
const $ = id => document.getElementById(id);
const articleId = item => item.p?.match(/ARTI\d+/)?.[0] || item.u.match(/ARTI\d+/)?.[0];
const safe = value => String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function dateOf(item) { const m = item.u.match(/\/(20\d\d)\/(\d\d)\/(\d\d)\//); return m ? `${m[1]}.${m[2]}.${m[3]}` : String(item.y); }
function filtered() { const q = state.query.toLocaleLowerCase('zh-CN'); return state.items.filter(a => (state.year === 'all' || String(a.y) === state.year) && (!q || (a.t + ' ' + a.d).toLocaleLowerCase('zh-CN').includes(q))); }
function articleRow(item) {
  const b = document.createElement('button'); b.className = 'art-item'; b.type = 'button';
  const title = document.createElement('span'); title.className = 'speech-row-title'; title.textContent = item.t;
  const subtitle = document.createElement('span'); subtitle.className = 'speech-row-subtitle'; subtitle.textContent = item.d;
  b.append(title,subtitle); b.onclick = () => openArticle(item);
  return b;
}
function renderList() {
  const rows = state.query ? filtered() : state.items;
  $('listTitle').textContent = state.query ? '搜索结果' : '目录';
  $('resultCount').textContent = rows.length + ' 篇';
  const frag = document.createDocumentFragment();
  if (state.query) {
    for (const item of rows.slice(0,state.visible)) frag.append(articleRow(item));
  } else {
    const years = [...new Set(rows.map(a=>a.y))].sort((a,b)=>b-a);
    for (const year of years) {
      const group = document.createElement('div'); group.className = 'year-block';
      const header = document.createElement('button'); header.className = 'yb-header'; header.type = 'button';
      header.innerHTML = '<h3>'+year+'年</h3><span class="yb-info">'+rows.filter(a=>a.y===year).length+' 篇　⌄</span>';
      const body = document.createElement('div'); body.className = 'yb-body'; body.hidden = year !== years[0];
      header.setAttribute('aria-expanded',String(!body.hidden));
      header.onclick = () => { body.hidden = !body.hidden; header.setAttribute('aria-expanded',String(!body.hidden)); if (!body.hidden && !body.childElementCount) rows.filter(a=>a.y===year).forEach(a=>body.append(articleRow(a))); };
      if (!body.hidden) rows.filter(a=>a.y===year).forEach(a=>body.append(articleRow(a)));
      group.append(header,body); frag.append(group);
    }
  }
  $('list').replaceChildren(frag);
  if (!rows.length) $('list').innerHTML = '<p class="speech-empty">没有找到相关讲话</p>';
  $('more').hidden = !state.query || rows.length <= state.visible;
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
    if (center) return '<p class="' + (/^\*\*/.test(center[1]) ? 'md-heading' : 'center') + '">' + inline(center[1]) + '</p>';
    if (s.startsWith('![')) return '<p class="center">' + inline(s) + '</p>';
    const heading = /^#{1,3} /.test(s);
    return '<p' + (heading ? ' class="md-heading"' : '') + '>' + inline(s.replace(/^#{1,3} /,'')) + '</p>';
  }).join('');
}
async function openArticle(item, replace = false) {
  state.current = state.items.indexOf(item);
  $('library').hidden = true; $('reader').hidden = false;
  document.body.classList.add('reading','article-active');
  closePanels();
  $('articleTitle').textContent = item.t; $('articleSubtitle').textContent = item.d; $('readerDate').textContent = dateOf(item);
  $('original').href = item.u;
  $('articleBody').innerHTML = '<p>正在加载正文…</p>';
  updateProgress();
  $('next').disabled = state.current <= 0;
  renderDirectory(item);
  renderRelated();
  if (replace) history.replaceState(null,'','#id='+articleId(item)); else history.pushState(null,'','#id='+articleId(item));
  window.scrollTo(0,0);
  if (!item.p) { $('articleBody').innerHTML = '<p>官网原文目前无法读取，请使用下方官网链接查看。</p>'; updateProgress(); return; }
  try {
    const response = await fetch('../' + item.p); if (!response.ok) throw Error(response.status);
    $('articleBody').innerHTML = renderBody(await response.text()); updateProgress();
  } catch (_) { $('articleBody').innerHTML = '<p>正文加载失败，请刷新或访问官网原文。</p>'; updateProgress(); }
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
  section.innerHTML = '<div class="ap-related-heading"><span class="ap-related-kicker">KEEP READING</span><h2 class="ap-related-title">相关阅读</h2></div><div class="ap-related-list"></div>';
  const list = section.querySelector('.ap-related-list');
  for (const entry of state.items.slice(state.current + 1, state.current + 4)) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'ap-related-item';
    const copy = document.createElement('span'); copy.className = 'ap-related-copy';
    const title = document.createElement('strong'); title.className = 'ap-related-name'; title.textContent = entry.t;
    const small = document.createElement('small'); small.className = 'ap-related-meta'; small.textContent = entry.d;
    const arrow = document.createElement('span'); arrow.className = 'ap-related-arrow'; arrow.textContent = '↗'; arrow.setAttribute('aria-hidden','true');
    copy.append(title,small); button.append(copy,arrow); button.onclick = () => openArticle(entry, true);
    list.append(button);
  }
}
function closePanels() {
  $('directoryPanel').hidden = true; $('settingsPanel').hidden = true;
  $('directory').setAttribute('aria-expanded','false'); $('settings').setAttribute('aria-expanded','false');
}
function showLibrary() {
  $('reader').hidden = true; $('library').hidden = false;
  document.body.classList.remove('reading','article-active'); closePanels();
  updateProgress();
  history.pushState(null,'','#'); window.scrollTo(0,0);
}
function applySettings() {
  const r = state.reading;
  document.documentElement.style.setProperty('--article-fs',r.font+'px');
  document.documentElement.style.setProperty('--article-lh',r.line);
  document.documentElement.style.setProperty('--article-indent',r.indent+'em');
  document.documentElement.dataset.readingPaper = r.paper;
  document.documentElement.dataset.theme = r.theme;
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
    renderList();
    const id = location.hash.match(/id=(ARTI\d+)/)?.[1]; if (id) { const item = state.items.find(a => articleId(a) === id); if (item) openArticle(item,true); }
  } catch (_) { $('list').innerHTML = '<p class="empty">目录暂时无法加载，请稍后重试。</p>'; }
}
$('query').oninput = e => { state.query = e.target.value.trim(); state.visible = 40; renderList(); };
function toggleSearch(open) {
  $('speechSearch').hidden = !open;
  $('searchToggle').setAttribute('aria-expanded', String(open));
  $('searchNav').classList.toggle('active', open);
  $('catalogNav').classList.toggle('active', !open);
  if (open) $('query').focus();
  else if (state.query) { $('query').value = ''; state.query = ''; renderList(); }
}
$('searchToggle').onclick = () => toggleSearch($('speechSearch').hidden);
$('searchNav').onclick = () => toggleSearch(true);
$('catalogNav').onclick = () => { toggleSearch(false); window.scrollTo({top:0,behavior:'smooth'}); };
$('more').onclick = () => { state.visible += 40; renderList(); };
$('back').onclick = showLibrary;
$('next').onclick = () => { if (state.current > 0) openArticle(state.items[state.current-1],true); };
$('directory').onclick = () => togglePanel('directoryPanel');
$('settings').onclick = () => togglePanel('settingsPanel');
$('toTop').onclick = () => window.scrollTo({top:0,behavior:'smooth'});
function updateProgress() {
  const reading = document.body.classList.contains('reading');
  $('toTop').classList.toggle('show', reading && scrollY >= 320);
  if (!reading) return;
  const body = $('articleBody').getBoundingClientRect();
  const start = body.top + scrollY;
  const end = Math.max(start + 1, body.bottom + scrollY - innerHeight);
  const progress = Math.max(0, Math.min(1, (scrollY - start) / (end - start)));
  $('progressRingFg').style.strokeDashoffset = String(131.95 * (1 - progress));
}
window.addEventListener('scroll',updateProgress,{passive:true});
document.querySelectorAll('[data-setting]').forEach(group => group.onclick = event => {
  const button = event.target.closest('button[data-value]');
  if (!button) return;
  state.reading[group.dataset.setting] = button.dataset.value;
  applySettings();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',applySettings);
window.onpopstate = () => { const id=location.hash.match(/id=(ARTI\d+)/)?.[1]; const item=state.items.find(a=>articleId(a)===id); if(item) openArticle(item,true); else { $('reader').hidden=true; $('library').hidden=false; document.body.classList.remove('reading','article-active'); closePanels(); } };
init();
