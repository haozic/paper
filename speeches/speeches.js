'use strict';
const VERSION = '20261123j';
const savedSettings = JSON.parse(localStorage.getItem('speech-reading') || '{}');
const settingKeys = {font:'reading_fontsize',theme:'reading_theme',line:'reading_lineheight',width:'reading_width',indent:'reading_indent',paper:'reading_paper'};
const stored = (key, fallback) => localStorage.getItem(settingKeys[key]) ?? savedSettings[key] ?? fallback;
const state = { items: [], current: -1, loadToken: 0, view: 'catalog', favorites: JSON.parse(localStorage.getItem('speech-favorites') || '[]'),
  reading: { font: stored('font','20'), theme: stored('theme','auto'), line: stored('line','2.05'), width: stored('width','0'), indent: stored('indent','2'), paper: stored('paper','default') } };
const speechRoot = document.getElementById('speechApp');
const $ = id => speechRoot.querySelector('#' + id);
const speechHash = id => '#m=speeches' + (id ? '&a=' + id : '');
const articleId = item => item.p?.match(/ARTI\d+/)?.[0] || item.u.match(/ARTI\d+/)?.[0];
const safe = value => String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function dateOf(item) { const m = item.u.match(/\/(20\d\d)\/(\d\d)\/(\d\d)\//); return m ? `${m[1]}.${m[2]}.${m[3]}` : String(item.y); }
function articleRow(item) {
  const b = document.createElement('button'); b.className = 'art-item'; b.type = 'button';
  const title = document.createElement('span'); title.className = 'speech-row-title'; title.textContent = item.t;
  const subtitle = document.createElement('span'); subtitle.className = 'speech-row-subtitle'; subtitle.textContent = item.d;
  b.append(title,subtitle); b.onclick = () => openArticle(item);
  return b;
}
function renderList() {
  const rows = state.items;
  const frag = document.createDocumentFragment();
  const years = [...new Set(rows.map(a=>a.y))].sort((a,b)=>b-a);
  for (const year of years) {
      const entries = rows.filter(a=>a.y===year);
      const group = document.createElement('div'); group.className = 'year-block' + (year === years[0] ? '' : ' collapsed');
      const header = document.createElement('div'); header.className = 'yb-header'; header.role = 'button'; header.tabIndex = 0;
      header.setAttribute('aria-expanded',String(year === years[0]));
      header.innerHTML = '<h3>'+year+'年</h3><div class="yb-right"><span class="yb-info">'+entries.length+'篇</span><span class="yb-toggle"><svg class="icon"><use href="#chevron-icon"/></svg></span></div>';
      const body = document.createElement('div'); body.className = 'yb-body';
      const articles = document.createElement('div'); articles.className = 'speech-year-articles'; body.append(articles);
      const expand = () => { const opening = group.classList.toggle('collapsed') === false; header.setAttribute('aria-expanded',String(opening)); if (opening && !articles.childElementCount) entries.forEach(a=>articles.append(articleRow(a))); };
      header.onclick = expand;
      header.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); expand(); } };
      if (year === years[0]) entries.forEach(a=>articles.append(articleRow(a)));
      group.append(header,body); frag.append(group);
  }
  $('list').replaceChildren(frag);
  if (!rows.length) $('list').innerHTML = '<p class="speech-empty">目录暂时无法加载</p>';
}
function inline(text) {
  return safe(text).replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, (_,alt,url) => `<img loading="lazy" src="${url}" alt="${alt}">`)
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function renderBody(md) {
  const blocks = md.split(/\n\s*\n/).map(block => block.trim()).filter(Boolean);
  const aligned = block => /^<div style="text-align:(center|right)">([\s\S]*?)<\/div>$/.exec(block);
  const content = block => aligned(block)?.[2] ?? block;
  const imageOnly = block => /^!\[[^\]]*\]\(https?:\/\/[^\s)]+\)$/.test(content(block));
  const parts = [];
  for (let i = 0; i < blocks.length; i++) {
    const s = blocks[i];
    if (imageOnly(s)) {
      let caption = '';
      const next = blocks[i + 1];
      const nextText = next && content(next);
      if (nextText && nextText.length <= 180 && !/^(!\[|#|\*\*)/.test(nextText) && !/text-align:right/.test(next)) {
        caption = '<figcaption>' + inline(nextText) + '</figcaption>';
        i++;
      }
      parts.push('<figure class="speech-figure">' + inline(content(s)) + caption + '</figure>');
      continue;
    }
    const alignment = aligned(s);
    if (alignment) {
      const cls = alignment[1] === 'right' ? 'right' : /^\*\*/.test(alignment[2]) ? 'speech-centered-heading' : 'center';
      parts.push('<p class="' + cls + '">' + inline(alignment[2]) + '</p>');
      continue;
    }
    const heading = /^#{1,3} /.test(s);
    parts.push('<p' + (heading ? ' class="md-heading"' : '') + '>' + inline(s.replace(/^#{1,3} /,'')) + '</p>');
  }
  return parts.join('');
}
async function openArticle(item, replace = false) {
  const token = ++state.loadToken;
  state.current = state.items.indexOf(item);
  $('library').hidden = true; $('reader').hidden = false;
  document.body.classList.add('reading','speech-reading');
  closePanels();
  $('articleTitle').textContent = item.t; $('articleSubtitle').textContent = item.d; $('readerDate').textContent = dateOf(item);
  $('speechOriginal').href = item.u;
  $('articleBody').innerHTML = '<p>正在加载正文…</p>';
  updateProgress();
  $('next').disabled = state.current <= 0;
  renderDirectory(item);
  renderRelated();
  updateFavoriteButton();
  if (replace) history.replaceState({speech:true},'',speechHash(articleId(item))); else history.pushState({speech:true},'',speechHash(articleId(item)));
  window.scrollTo(0,0);
  if (!item.p) { $('articleBody').innerHTML = '<p>官网原文目前无法读取，请使用下方官网链接查看。</p>'; updateProgress(); return; }
  try {
    let response = await fetch(item.p + '?v=' + VERSION); if (!response.ok) throw Error(response.status);
    let markdown = await response.text();
    // An older service worker keyed speech Markdown by path and may still serve
    // a corrupted copy during the first load after this release.
    if (speechBodyLooksCorrupt(markdown) && 'caches' in window) {
      await caches.open('djyj-md-v2').then(cache => cache.delete(new URL(item.p, location.href).href));
      response = await fetch(item.p + '?v=' + VERSION + '&repair=1', { cache: 'reload' });
      if (!response.ok) throw Error(response.status);
      markdown = await response.text();
    }
    if (speechBodyLooksCorrupt(markdown)) throw Error('Corrupt speech body');
    if (token === state.loadToken) { $('articleBody').innerHTML = renderBody(markdown); updateProgress(); }
  } catch (_) { if (token === state.loadToken) { $('articleBody').innerHTML = '<p>正文加载失败，请刷新或访问官网原文。</p>'; updateProgress(); } }
}

function speechBodyLooksCorrupt(body) {
  const chinese = (body.match(/[\u3400-\u9fff]/g) || []).length;
  return body.length < 100 || body.includes('�') || chinese < 50 || chinese / body.length < 0.2;
}
function renderDirectory(item) {
  $('directoryTitle').textContent = '习近平讲话库 · ' + item.y + '年';
  const entries = state.items.filter(a => a.y === item.y);
  $('directoryCount').textContent = entries.length + ' 篇';
  const list = document.createDocumentFragment();
  entries.forEach((entry, index) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'reading-issue-item' + (entry === item ? ' active' : '');
    if (entry === item) button.setAttribute('aria-current','page');
    const number = document.createElement('span'); number.className = 'reading-issue-number'; number.textContent = String(index+1).padStart(2,'0');
    const title = document.createElement('span'); title.className = 'reading-issue-title'; title.textContent = entry.t;
    button.append(number,title);
    button.onclick = () => openArticle(entry, true);
    list.append(button);
  });
  $('directoryList').className = 'reading-issue-list';
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
  state.loadToken++;
  $('reader').hidden = true; $('library').hidden = false;
  document.body.classList.remove('reading','speech-reading'); closePanels();
  updateProgress();
  history.pushState({speech:true},'',speechHash()); window.scrollTo(0,0);
}
function applySettings() {
  const r = state.reading;
  document.documentElement.style.setProperty('--article-fs',r.font+'px');
  document.documentElement.style.setProperty('--article-lh',r.line);
  document.documentElement.style.setProperty('--article-w-delta',r.width+'px');
  document.documentElement.style.setProperty('--article-indent',r.indent+'em');
  document.documentElement.dataset.articleWidth = Number(r.width) < 0 ? 'narrow' : Number(r.width) > 0 ? 'wide' : 'standard';
  document.documentElement.dataset.readingPaper = r.paper;
  document.documentElement.dataset.theme = r.theme;
  speechRoot.querySelectorAll('[data-setting]').forEach(group => {
    group.querySelectorAll('button').forEach(b => b.classList.toggle('active',b.dataset.value === r[group.dataset.setting]));
  });
  for (const [key, value] of Object.entries(r)) localStorage.setItem(settingKeys[key], value);
}
function togglePanel(id) {
  const opening = $(id).hidden; closePanels();
  $(id).hidden = !opening;
  $(id === 'directoryPanel' ? 'directory' : 'settings').setAttribute('aria-expanded',String(opening));
  if (opening && id === 'directoryPanel') $('directoryList').querySelector('[aria-current="page"]')?.scrollIntoView({block:'nearest'});
}
async function init() {
  applySettings();
  $('list').innerHTML = '<div class="loading" role="status">目录加载中…</div>';
  try {
    const url = 'data/speeches/index.json?v='+VERSION;
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const response = await fetch(url, attempt ? {cache:'reload'} : undefined);
        if (!response.ok) throw Error(response.status);
        const items = (await response.json()).items;
        if (!Array.isArray(items) || !items.length) throw Error('Invalid speech catalog');
        state.items = items;
        break;
      } catch (error) {
        if (attempt) throw error;
        if ('caches' in window) {
          try {
            const key = new URL(url, location.href).href;
            await Promise.all((await caches.keys()).map(async name => (await caches.open(name)).delete(key)));
          } catch (_) { /* Retry even when cache access is unavailable. */ }
        }
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    }
    const years = state.items.map(item => item.y);
    $('count').textContent = state.items.length + ' 篇 · ' + Math.min(...years) + '—' + Math.max(...years);
    renderList();
    if (state.view === 'favorites') renderFavorites();
    window.__speechRoute?.();
  } catch (error) {
    console.error('讲话库目录加载失败:', error);
    $('list').innerHTML = '<div class="loading" role="alert">目录加载失败。<button type="button">重试加载</button></div>';
    $('list').querySelector('button').onclick = init;
  }
}
function showView(view) {
  state.view = view;
  $('catalogView').classList.toggle('active',view === 'catalog');
  $('favoritesView').classList.toggle('active',view === 'favorites');
  $('catalogTab').classList.toggle('active',view === 'catalog');
  $('favoritesTab').classList.toggle('active',view === 'favorites');
  $('catalogNav').classList.toggle('active',view === 'catalog');
  $('favoritesNav').classList.toggle('active',view === 'favorites');
  if (view === 'favorites') renderFavorites();
  window.scrollTo(0,0);
}
function renderFavorites() {
  const list = $('favoritesList');
  const favorites = state.favorites.map(id => state.items.find(a => articleId(a) === id)).filter(Boolean);
  if (!favorites.length) { list.innerHTML = '<div class="fav-empty"><div class="fav-empty-text">还没有收藏文章</div><div class="fav-empty-hint">阅读时可在设置面板收藏</div></div>'; return; }
  list.replaceChildren(...favorites.map(articleRow));
}
function updateFavoriteButton() {
  const item = state.items[state.current];
  const active = !!item && state.favorites.includes(articleId(item));
  $('speechFav').classList.toggle('active',active);
  $('speechFav').setAttribute('aria-pressed',String(active));
  $('speechFav').querySelector('span').textContent = active ? '已收藏' : '收藏';
}
function toggleFavorite() {
  const item = state.items[state.current]; if (!item) return;
  const id = articleId(item);
  state.favorites = state.favorites.includes(id) ? state.favorites.filter(x=>x!==id) : [...state.favorites,id];
  localStorage.setItem('speech-favorites',JSON.stringify(state.favorites));
  updateFavoriteButton();
}
async function shareArticle() {
  const item = state.items[state.current]; if (!item) return;
  const data = {title:item.t,url:location.href};
  try {
    if (navigator.share) await navigator.share(data);
    else {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(data.url);
      else { const input = document.createElement('textarea'); input.value = data.url; document.body.append(input); input.select(); document.execCommand('copy'); input.remove(); }
      $('speechShare').classList.add('copied'); setTimeout(()=>$('speechShare').classList.remove('copied'),1800);
    }
  } catch (_) { /* Cancelled share leaves the reader unchanged. */ }
}
$('searchToggle').onclick = () => openGlobalSearch();
$('catalogNav').onclick = () => { closeGlobalSearch(); showView('catalog'); };
$('favoritesNav').onclick = () => { closeGlobalSearch(); showView('favorites'); };
$('catalogTab').onclick = () => { closeGlobalSearch(); showView('catalog'); };
$('favoritesTab').onclick = () => { closeGlobalSearch(); showView('favorites'); };
$('aboutToggle').onclick = () => { closeGlobalSearch(); showAboutPage(); };
$('back').onclick = showLibrary;
$('next').onclick = () => { if (state.current > 0) openArticle(state.items[state.current-1],true); };
$('directory').onclick = () => togglePanel('directoryPanel');
$('settings').onclick = () => togglePanel('settingsPanel');
$('settingsClose').onclick = closePanels;
$('speechFav').onclick = toggleFavorite;
$('speechShare').onclick = shareArticle;
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
speechRoot.querySelectorAll('[data-setting]').forEach(group => group.onclick = event => {
  const button = event.target.closest('button[data-value]');
  if (!button) return;
  state.reading[group.dataset.setting] = button.dataset.value;
  applySettings();
});
document.addEventListener('click', event => { if (document.body.classList.contains('speech-reading') && !event.target.closest('.reading-dock')) closePanels(); });
document.addEventListener('keydown', event => { if (document.body.classList.contains('speech-active') && event.key === 'Escape') closePanels(); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',applySettings);
window.__speechRoute = () => { if (!state.items.length) return; const params = new URLSearchParams(location.hash.slice(1)); const id = params.get('a'); const item = state.items.find(a => articleId(a) === id); if (item) { if (state.items[state.current] !== item || $('reader').hidden) openArticle(item,true); } else { state.loadToken++; $('reader').hidden=true; $('library').hidden=false; document.body.classList.remove('reading','speech-reading'); closePanels(); showView('catalog'); } };
init();
