'use strict';

/* ===== 全局缓存版本号（与 index.html 一致，用于 data/*.json 缓存破坏） ===== */
const DATA_VERSION = (typeof window !== 'undefined' && window.__DATA_VERSION__) || '20260907b';
function dataUrl(p) { return p + (p.includes('?') ? '&' : '?') + 'v=' + DATA_VERSION; }

/* ===== 杂志配置 ===== */
const MAGAZINES = {
    qs: {
        name: '求是',
        fullName: '《求是》',
        color: '#8b0000',
        colorDark: '#8b0000',
        dataPath: 'data/qs',
        yearsPath: 'data/qs/years',
        source: 'https://www.qstheory.cn/qs/mulu.htm',
        desc: '中共中央委员会机关刊',
    },
    hqwg: {
        name: '红旗文稿',
        fullName: '《红旗文稿》',
        color: '#8b0000',
        colorDark: '#8b0000',
        dataPath: 'data/hqwg',
        yearsPath: 'data/hqwg/years',
        source: 'https://www.qstheory.cn/hqwglist/mulu.htm',
        desc: '政治理论半月刊',
    },
    djyj: {
        name: '党建研究',
        fullName: '《党建研究》',
        color: '#8b0000',
        colorDark: '#8b0000',
        dataPath: 'data',
        yearsPath: 'data/years',
        source: 'https://djyj.12371.cn/',
        desc: '党建理论与实践研究月刊',
    },
};

/* ===== 状态管理 ===== */
const state = {
    currentMag: null,       // null=首页, 'qs'|'hqwg'|'djyj'
    magCache: {},           // {qs: {meta, yearData, loadedYears, fullTextReady}, ...}
    favorites: [],
    currentMode: 'section',
    currentArticleUrl: null,
    fullTextReady: false,
    catalogRendered: false,
    catalogPending: false,
    catalogExpanded: new Set(),
    isSearching: false,
    searchResults: [],
    currentPage: 1,
    pageSize: 20,
    readingFs: 20,          // 文章字号
    readingTheme: 'auto',   // light / dark / auto
};

const CN = ['一','二','三','四','五','六','七','八','九','十','十一','十二','十三','十四','十五','十六','十七','十八','十九','二十','二十一','二十二','二十三','二十四'];
const FAV_KEY = 'djyj_favorites';

/* ===== SVG 辅助 ===== */
function svgStar(filled) {
    return `<svg class="icon"><use href="#${filled ? 'i-star-fill' : 'i-star'}"/></svg>`;
}
function svgIcon(name) {
    return `<svg class="icon"><use href="#${name}"/></svg>`;
}

/* ===== 当前杂志数据快捷访问 ===== */
function getMagState() {
    if (!state.currentMag) return null;
    if (!state.magCache[state.currentMag]) {
        state.magCache[state.currentMag] = {
            meta: [],
            yearData: {},
            loadedYears: new Set(),
            loadingYears: new Set(),
            fullTextReady: false,
            articleIndex: null,
            indexLoaded: false,
        };
    }
    return state.magCache[state.currentMag];
}

function getMeta() { return getMagState()?.meta || []; }
function getYearData() { return getMagState()?.yearData || {}; }

/* ===== 首页：加载各杂志计数 ===== */
async function loadHomeCounts() {
    for (const [key, conf] of Object.entries(MAGAZINES)) {
        try {
            const resp = await fetch(dataUrl(`${conf.dataPath}/meta.json`));
            const meta = await resp.json();
            // 缓存 meta 到 magCache，供收藏列表跨杂志查找
            if (!state.magCache[key]) {
                state.magCache[key] = {
                    meta: [],
                    yearData: {},
                    loadedYears: new Set(),
                    loadingYears: new Set(),
                    fullTextReady: false,
                    articleIndex: null,
                    indexLoaded: false,
                };
            }
            state.magCache[key].meta = meta;
            const countEl = document.getElementById(`${key}Count`);
            const issuesEl = document.getElementById(`${key}Issues`);
            if (countEl) countEl.textContent = meta.length;
            if (issuesEl) {
                const issues = [...new Set(meta.map(a => `${a.y}-${a.i}`))].length;
                issuesEl.textContent = issues;
            }
        } catch (e) {
            console.error(`加载 ${key} 计数失败:`, e);
        }
    }
}

/* ===== 进入/退出杂志 ===== */
function enterMagazine(magKey) {
    state.currentMag = magKey;
    const conf = MAGAZINES[magKey];

    // 重置状态
    state.catalogRendered = false;
    state.catalogPending = false;
    state.catalogExpanded = new Set();
    state.isSearching = false;
    state.currentMode = 'section';
    state.searchResults = [];
    state.currentPage = 1;

    // 显示应用页
    document.body.classList.add('mag-active');

    // 更新标题
    document.getElementById('magTitle').textContent = conf.fullName;
    document.documentElement.style.setProperty('--mag-color-base', conf.color);
    document.documentElement.style.setProperty('--mag-color-dark-base', conf.colorDark);

    // 清空搜索
    document.getElementById('searchInput').value = '';
    document.getElementById('searchStatus').textContent = '加载中...';
    document.getElementById('searchStatus').className = 'search-status';

    // 重置视图
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('sectionView').classList.add('active');
    document.querySelectorAll('.nav-tab, .bn-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === 'section');
    });

    // 加载数据
    initMagazine(magKey);

    // History
    history.pushState({ mag: magKey }, '', `#m=${magKey}`);
    window.scrollTo(0, 0);
}

function goHome() {
    // 关闭所有覆盖层
    document.body.classList.remove('article-active', 'section-active', 'about-active', 'mag-active');
    state.currentMag = null;

    // 重置杂志颜色
    document.documentElement.style.setProperty('--mag-color-base', '#8b0000');
    document.documentElement.style.setProperty('--mag-color-dark-base', '#8b0000');

    history.pushState({ home: true }, '', '#');
    window.scrollTo(0, 0);
}

async function initMagazine(magKey) {
    const conf = MAGAZINES[magKey];
    const ms = getMagState();

    if (ms.meta.length === 0) {
        try {
            const resp = await fetch(dataUrl(`${conf.dataPath}/meta.json`));
            ms.meta = await resp.json();
        } catch (e) {
            console.error('加载元数据失败:', e);
            document.getElementById('sectionContent').innerHTML =
                '<div class="loading"><div>数据加载失败，请刷新重试</div></div>';
            return;
        }
    }

    // 后台加载文章索引（不阻塞）
    if (!ms.indexLoaded) {
        ms.indexLoaded = true;
        fetch(dataUrl('data/article_index.json'))
            .then(r => r.ok ? r.json() : null)
            .then(idx => {
                if (idx) ms.articleIndex = idx[magKey] || {};
            })
            .catch(() => {});
    }

    document.getElementById('totalCount').textContent = ms.meta.length;

    // 如果用户已在目录视图，重新渲染目录
    if (state.catalogPending && state.currentMode === 'catalog') {
        state.catalogPending = false;
        renderCatalog();
    }

    // 默认显示板块
    renderSections();
    loadAllYearsBackground();
    updateStickyOffsets();

    // 字体加载后重新测量（字体加载会改变 header 实际高度）
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => updateStickyOffsets());
    }
    // 延迟再测一次，确保布局稳定
    requestAnimationFrame(() => requestAnimationFrame(updateStickyOffsets));
}

/* ===== 动态测量 sticky 偏移量 ===== */
function updateStickyOffsets() {
    const header = document.querySelector('.app-header');
    const searchBar = document.getElementById('searchBar');
    if (!header) return;
    const headerH = header.offsetHeight;
    document.documentElement.style.setProperty('--header-h', headerH + 'px');
    if (searchBar) {
        const searchH = searchBar.offsetHeight;
        document.documentElement.style.setProperty('--search-h', searchH + 'px');
    }
}

/* ===== 数据加载 ===== */
async function loadYearData(year, retry = 2) {
    const ms = getMagState();
    if (!ms) return false;
    const conf = MAGAZINES[state.currentMag];
    year = String(year);
    if (ms.loadedYears.has(year) || ms.loadingYears.has(year)) return ms.loadedYears.has(year);
    ms.loadingYears.add(year);
    try {
        const resp = await fetch(dataUrl(`${conf.yearsPath}/${year}.json`));
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        ms.yearData[year] = await resp.json();
        ms.loadedYears.add(year);
        return true;
    } catch (e) {
        console.error(`加载 ${year} 年数据失败:`, e);
        if (retry > 0) {
            await new Promise(r => setTimeout(r, 800));
            ms.loadingYears.delete(year);
            return loadYearData(year, retry - 1);
        }
        return false;
    } finally {
        ms.loadingYears.delete(year);
    }
}

async function loadAllYearsBackground() {
    const ms = getMagState();
    if (!ms) return;
    const status = document.getElementById('searchStatus');
    status.className = 'search-status ready';
    status.textContent = '标题搜索就绪 · 正文搜索按需加载';

    // 不再自动加载所有年份数据
    // 正文搜索时按需加载对应年份
    ms.fullTextReady = false;
    state.fullTextReady = false;

    const q = document.getElementById('searchInput').value.trim();
    if (q) performSearch();
}

/* ===== 收藏管理 ===== */
function loadFavorites() {
    try {
        const data = localStorage.getItem(FAV_KEY);
        state.favorites = data ? JSON.parse(data) : [];
    } catch (e) {
        state.favorites = [];
    }
}

function saveFavorites() {
    try {
        localStorage.setItem(FAV_KEY, JSON.stringify(state.favorites));
    } catch (e) {}
    updateFavBadges();
}

function isFavorite(url) {
    return state.favorites.includes(url);
}

function toggleFavorite(url) {
    const idx = state.favorites.indexOf(url);
    if (idx >= 0) state.favorites.splice(idx, 1);
    else state.favorites.unshift(url);
    saveFavorites();
}

function updateFavBadges() {
    const count = state.favorites.length;
    document.querySelectorAll('.fav-badge').forEach(b => {
        b.textContent = count;
        b.setAttribute('data-count', count);
    });
}

/* ===== 搜索 ===== */
function getSearchScope() {
    const checked = document.querySelector('input[name="searchScope"]:checked');
    return checked ? checked.value : 'all';
}

function performSearch() {
    const input = document.getElementById('searchInput');
    const query = input.value.trim().toLowerCase();
    const hasQuery = query.length > 0;
    const ms = getMagState();
    if (!ms) return;

    if (hasQuery && !state.isSearching) {
        state.isSearching = true;
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById('searchView').classList.add('active');
    } else if (!hasQuery && state.isSearching) {
        state.isSearching = false;
        state.searchResults = [];
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const viewMap = { section: 'sectionView', catalog: 'catalogView', favorites: 'favoritesView' };
        const view = document.getElementById(viewMap[state.currentMode]);
        if (view) view.classList.add('active');
        document.getElementById('resultInfo').textContent = '';
        document.getElementById('searchResults').innerHTML = '';
        document.getElementById('pagination').innerHTML = '';
        return;
    }

    if (!hasQuery) return;

    const scope = getSearchScope();
    const bo = document.getElementById('bodyOnly').checked;

    // 标题搜索：立即执行
    let results;
    if (scope === 'title') {
        results = ms.meta.filter(a => {
            if (bo && !a.h) return false;
            const metaData = (a.t + ' ' + a.a + ' ' + a.s).toLowerCase();
            return metaData.includes(query);
        });
    } else if (scope === 'all') {
        // 标题+正文：先搜标题，同时检查已加载的正文
        results = ms.meta.filter(a => {
            if (bo && !a.h) return false;
            const metaData = (a.t + ' ' + a.a + ' ' + a.s).toLowerCase();
            if (metaData.includes(query)) return true;
            if (a.h) {
                const yd = ms.yearData[String(a.y)];
                if (yd && yd[a.u]) {
                    if (yd[a.u].toLowerCase().includes(query)) return true;
                }
            }
            return false;
        });
        // 如果正文数据未完全加载，提示用户
        if (!ms.fullTextReady) {
            performBodySearch(query, results, scope, bo);
            return;
        }
    } else if (scope === 'body') {
        // 仅正文：需要正文数据
        if (!ms.fullTextReady) {
            performBodySearch(query, [], scope, bo);
            return;
        }
        results = ms.meta.filter(a => {
            if (bo && !a.h) return false;
            if (!a.h) return false;
            const yd = ms.yearData[String(a.y)];
            if (yd && yd[a.u]) {
                return yd[a.u].toLowerCase().includes(query);
            }
            return false;
        });
    } else {
        results = ms.meta.filter(a => !bo || a.h);
    }

    finishSearch(results, query, scope, input);
}

async function performBodySearch(query, initialResults, scope, bo) {
    const ms = getMagState();
    if (!ms) return;
    const input = document.getElementById('searchInput');
    const infoEl = document.getElementById('resultInfo');

    // 先显示标题搜索结果，不让学生等
    if (initialResults && initialResults.length > 0) {
        state.searchResults = initialResults;
        state.currentPage = 1;
        const qDisplay = input.value.trim();
        infoEl.textContent = `共 ${initialResults.length} 篇（标题匹配）· 正在加载正文数据搜索更多...`;
        renderSearchPage();
    } else {
        infoEl.textContent = '正在加载正文数据用于搜索...';
        document.getElementById('searchResults').innerHTML = '<div class="loading"><div class="spinner"></div><div>加载正文数据中...</div></div>';
    }

    // 并行加载所有未加载的年份
    const years = [...new Set(ms.meta.filter(a => a.h).map(a => a.y))].sort((a, b) => b - a);
    const loadPromises = [];
    for (const y of years) {
        if (!ms.loadedYears.has(String(y))) {
            loadPromises.push(loadYearData(y));
        }
    }
    if (loadPromises.length > 0) {
        await Promise.all(loadPromises);
    }
    ms.fullTextReady = true;
    state.fullTextReady = true;
    document.getElementById('searchStatus').textContent = '全文搜索就绪';

    // 重新搜索
    const results = ms.meta.filter(a => {
        if (bo && !a.h) return false;
        let matched = false;
        if (scope === 'all') {
            const metaData = (a.t + ' ' + a.a + ' ' + a.s).toLowerCase();
            if (metaData.includes(query)) matched = true;
        }
        if (!matched && a.h) {
            const yd = ms.yearData[String(a.y)];
            if (yd && yd[a.u]) {
                if (yd[a.u].toLowerCase().includes(query)) matched = true;
            }
        }
        return matched;
    });

    finishSearch(results, query, scope, input);
}

function finishSearch(results, query, scope, input) {
    state.searchResults = results;
    state.currentPage = 1;

    const qDisplay = input.value.trim();
    const scopeLabel = scope === 'all' ? '标题+正文' : (scope === 'title' ? '仅标题' : '仅正文');
    let infoText = `共 ${results.length} 篇文章`;
    if (qDisplay) infoText += `（关键词："${qDisplay}" ｜ 范围：${scopeLabel}）`;
    if (scope !== 'title' && !state.fullTextReady) infoText += ' · 全文搜索加载中，当前仅搜索标题/作者';
    document.getElementById('resultInfo').textContent = infoText;

    renderSearchPage();
}

function renderSearchPage() {
    const results = state.searchResults;
    const container = document.getElementById('searchResults');
    const pagination = document.getElementById('pagination');
    const query = document.getElementById('searchInput').value.trim().toLowerCase();
    const scope = getSearchScope();
    const ms = getMagState();

    if (results.length === 0) {
        container.innerHTML = '<div class="loading"><div>未找到匹配文章</div></div>';
        pagination.innerHTML = '';
        return;
    }

    const totalPages = Math.ceil(results.length / state.pageSize);
    if (state.currentPage > totalPages) state.currentPage = totalPages;
    if (state.currentPage < 1) state.currentPage = 1;

    const start = (state.currentPage - 1) * state.pageSize;
    const end = Math.min(start + state.pageSize, results.length);
    const pageResults = results.slice(start, end);

    let html = '';
    pageResults.forEach(a => {
        let titleHtml = escHtml(a.t);
        let snippet = '';
        let authorHtml = a.a ? `<span class="rc-author">｜${escHtml(a.a)}</span>` : '';

        if (query) {
            titleHtml = highlightText(a.t, query);
            if (a.h && (scope === 'body' || scope === 'all')) {
                const yd = ms.yearData[String(a.y)];
                const body = (yd && yd[a.u]) ? yd[a.u] : '';
                if (body) {
                    const lb = body.toLowerCase();
                    const pos = lb.indexOf(query);
                    if (pos >= 0) {
                        const s = Math.max(0, pos - 40);
                        const e = Math.min(body.length, pos + query.length + 80);
                        snippet = (s > 0 ? '...' : '') + body.substring(s, e) + (e < body.length ? '...' : '');
                        snippet = highlightText(snippet, query);
                    } else {
                        snippet = escHtml(body.substring(0, 120)) + '...';
                    }
                }
            }
            if (!snippet) {
                if (scope === 'title') snippet = '';
                else if (!a.h) snippet = '<span style="color:var(--text-3);">无正文</span>';
            }
        }

        const ci = a.i <= 24 ? CN[a.i - 1] : a.i;
        const isFav = isFavorite(a.u);
        const favClass = isFav ? 'active' : '';
        const favIcon = svgStar(isFav);
        const noBodyTag = a.h ? '' : '<span class="rc-tag no-body">无全文</span>';
        const encUrl = encodeURIComponent(a.u);
        const snippetHtml = snippet ? `<div class="rc-snippet">${snippet}</div>` : '';

        html += `<div class="result-card" onclick="showArticle('${encUrl}')">
            <button class="rc-fav-btn ${favClass}" onclick="event.stopPropagation(); toggleFavFromCard(this, '${encUrl}')">${favIcon}</button>
            <div class="rc-title">${titleHtml}</div>
            <div class="rc-meta">
                <span class="rc-tag">${a.y}年第${ci}期</span>
                <span class="rc-tag">${escHtml(a.s)}</span>
                ${authorHtml}
                ${noBodyTag}
            </div>
            ${snippetHtml}
        </div>`;
    });

    container.innerHTML = html;
    renderPagination(totalPages);
}

function renderPagination(totalPages) {
    const pagination = document.getElementById('pagination');
    if (totalPages <= 1) {
        pagination.innerHTML = `<span class="page-info">共 ${state.searchResults.length} 条</span>`;
        return;
    }
    let html = '';
    const cur = state.currentPage;
    html += `<button class="page-btn" onclick="goToPage(${cur - 1})" ${cur <= 1 ? 'disabled' : ''}><svg class="icon" style="width:14px;height:14px;transform:rotate(90deg);"><use href="#i-chevron"/></svg></button>`;
    const pages = [];
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
        pages.push(1);
        if (cur > 4) pages.push('...');
        const start = Math.max(2, cur - 1);
        const end = Math.min(totalPages - 1, cur + 1);
        for (let i = start; i <= end; i++) pages.push(i);
        if (cur < totalPages - 3) pages.push('...');
        pages.push(totalPages);
    }
    pages.forEach(p => {
        if (p === '...') html += '<span class="page-ellipsis">…</span>';
        else html += `<button class="page-btn ${p === cur ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
    });
    html += `<button class="page-btn" onclick="goToPage(${cur + 1})" ${cur >= totalPages ? 'disabled' : ''}><svg class="icon" style="width:14px;height:14px;transform:rotate(-90deg);"><use href="#i-chevron"/></svg></button>`;
    html += `<span class="page-info">${cur}/${totalPages} 页 · 共 ${state.searchResults.length} 条</span>`;
    pagination.innerHTML = html;
}

function goToPage(page) {
    const totalPages = Math.ceil(state.searchResults.length / state.pageSize);
    if (page < 1 || page > totalPages) return;
    state.currentPage = page;
    renderSearchPage();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleFavFromCard(btn, encUrl) {
    const url = decodeURIComponent(encUrl);
    toggleFavorite(url);
    const active = isFavorite(url);
    btn.classList.toggle('active', active);
    btn.innerHTML = svgStar(active);
}

/* ===== 文章详情 ===== */
async function showArticle(encUrl) {
    const url = decodeURIComponent(encUrl);
    let ms = getMagState();
    let idx = -1;

    // 在当前杂志中查找
    if (ms && ms.meta.length > 0) {
        idx = ms.meta.findIndex(a => a.u === url);
    }

    // 跨杂志查找（如从收藏列表点击）
    if (idx < 0) {
        for (const [magKey, magState] of Object.entries(state.magCache)) {
            if (magState.meta.length > 0) {
                const found = magState.meta.findIndex(a => a.u === url);
                if (found >= 0) {
                    if (state.currentMag !== magKey) {
                        enterMagazine(magKey);
                        setTimeout(() => showArticle(encUrl), 600);
                        return;
                    }
                    ms = magState;
                    idx = found;
                    break;
                }
            }
        }
    }

    // meta 尚未加载，等待重试
    if (!ms || ms.meta.length === 0) {
        setTimeout(() => showArticle(encUrl), 500);
        return;
    }
    if (idx < 0) return;
    const a = ms.meta[idx];

    state.currentArticleUrl = url;
    state.currentArticleIdx = idx;

    document.getElementById('articleTitle').textContent = a.t;
    updateArticleMeta(a, 0);

    const origLink = document.getElementById('articleOrigLink');
    if (a.u) { origLink.href = a.u; origLink.style.display = ''; }
    else origLink.style.display = 'none';

    const favBtn = document.getElementById('articleFavBtn');
    const isFav = isFavorite(url);
    favBtn.classList.toggle('active', isFav);
    favBtn.innerHTML = svgStar(isFav);

    const bodyEl = document.getElementById('articleBody');
    document.body.classList.add('article-active');
    window.scrollTo(0, 0);

    const magKey = state.currentMag;
    if (!history.state || history.state.articleUrl !== url) {
        history.pushState({ articleUrl: url, mag: magKey }, '', `#m=${magKey}&a=${idx}`);
    }

    if (!a.h) {
        bodyEl.innerHTML = '<div class="no-body">该文章无全文内容<br><small>可能为新闻汇总条目或专刊文献</small></div>';
        return;
    }

    bodyEl.innerHTML = '<div class="article-loading"><div class="spinner"></div><div>加载正文...</div></div>';

    // 优先从 markdown 文件加载（轻量，单文件按需加载）
    const mdPath = ms.articleIndex?.[url];
    if (mdPath) {
        try {
            const resp = await fetch(mdPath);
            if (resp.ok) {
                let md = await resp.text();
                // 统一换行符：CRLF -> LF，避免 Windows 行尾导致分隔符检测失败
                md = md.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
                // 去掉 markdown 头部的元信息（# 标题到 --- 分隔线之间的内容）
                let bodyMd = md;
                const sepIdx = md.indexOf('\n---\n');
                if (sepIdx >= 0) bodyMd = md.substring(sepIdx + 5).trim();
                bodyEl.innerHTML = renderMarkdown(bodyMd);
                const wordCount = countWords(bodyEl.textContent);
                updateArticleMeta(a, wordCount);
                return;
            }
        } catch (e) {
            console.error('加载 markdown 文件失败:', e);
        }
    }

    // 回退到 year JSON 数据
    if (!ms.loadedYears.has(String(a.y))) {
        const ok = await loadYearData(a.y);
        if (!ok) {
            bodyEl.innerHTML = `<div class="no-body">正文数据加载失败<br>
                <small>可能是网络不稳定，请重试</small><br>
                <button class="retry-btn" onclick="retryShowArticle('${encUrl}')">重新加载</button></div>`;
            return;
        }
    }

    renderArticleBody(url, a.y, bodyEl);
}

function updateArticleMeta(a, wordCount) {
    const ci = a.i <= 24 ? CN[a.i - 1] : a.i;
    let meta = `${a.y}年第${ci}期 ｜ ${escHtml(a.s)}${a.a ? ' ｜ ' + escHtml(a.a) : ''}`;
    if (wordCount > 0) meta += ` ｜ 约 ${wordCount} 字`;
    document.getElementById('articleMeta').innerHTML = meta;
}

function countWords(text) {
    if (!text) return 0;
    return text.replace(/\s/g, '').length;
}

function renderArticleBody(url, year, bodyEl) {
    const ms = getMagState();
    if (!ms) return;
    const yd = ms.yearData[String(year)];
    if (yd && yd[url]) {
        const body = yd[url].replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        bodyEl.innerHTML = renderMarkdown(body);
        const a = ms.meta.find(x => x.u === url);
        if (a) {
            const wordCount = countWords(bodyEl.textContent);
            updateArticleMeta(a, wordCount);
        }
    } else {
        bodyEl.innerHTML = `<div class="no-body">未找到该文章的正文数据<br>
            <small>URL: ${escHtml(url.substring(0, 60))}...</small></div>`;
    }
}

async function retryShowArticle(encUrl) {
    const url = decodeURIComponent(encUrl);
    const ms = getMagState();
    if (!ms) return;
    const a = ms.meta.find(x => x.u === url);
    if (!a) return;
    const bodyEl = document.getElementById('articleBody');
    bodyEl.innerHTML = '<div class="article-loading"><div class="spinner"></div><div>重新加载中...</div></div>';

    // 优先重试 markdown 文件
    const mdPath = ms.articleIndex?.[url];
    if (mdPath) {
        try {
            const resp = await fetch(mdPath + '?t=' + Date.now());
            if (resp.ok) {
                let md = await resp.text();
                md = md.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
                let bodyMd = md;
                const sepIdx = md.indexOf('\n---\n');
                if (sepIdx >= 0) bodyMd = md.substring(sepIdx + 5).trim();
                bodyEl.innerHTML = renderMarkdown(bodyMd);
                const wordCount = countWords(bodyEl.textContent);
                updateArticleMeta(a, wordCount);
                return;
            }
        } catch (e) {}
    }

    // 回退到 year JSON
    ms.loadedYears.delete(String(a.y));
    delete ms.yearData[String(a.y)];
    const ok = await loadYearData(a.y);
    if (!ok) {
        bodyEl.innerHTML = `<div class="no-body">加载仍然失败<br>
            <small>请检查网络后重试，或访问原文链接</small><br>
            <button class="retry-btn" onclick="retryShowArticle('${encUrl}')">再次重试</button>
            <a href="${a.u}" target="_blank" rel="noopener" style="display:inline-block;margin-top:10px;color:var(--primary);">直接查看原文</a></div>`;
        return;
    }
    renderArticleBody(url, a.y, bodyEl);
}

function toggleArticleFav() {
    if (!state.currentArticleUrl) return;
    const url = state.currentArticleUrl;
    toggleFavorite(url);
    const isFav = isFavorite(url);
    const btn = document.getElementById('articleFavBtn');
    btn.classList.toggle('active', isFav);
    btn.innerHTML = svgStar(isFav);
    if (state.currentMode === 'favorites' && !state.isSearching) renderFavorites();
    if (state.isSearching) performSearch();
}

function goBack() {
    if (document.body.classList.contains('article-active') ||
        document.body.classList.contains('section-active') ||
        document.body.classList.contains('about-active')) {
        history.back();
    } else if (state.currentMag) {
        goHome();
    }
}

function closeArticlePage() {
    document.body.classList.remove('article-active');
    state.currentArticleUrl = null;
    const ring = document.getElementById('progressRingFg');
    if (ring) ring.style.strokeDashoffset = RING_CIRCUMFERENCE;
    document.getElementById('backToTopBtn')?.classList.remove('show');
    // 关闭设置面板
    document.getElementById('articleSettingsPanel')?.classList.remove('show');
    document.getElementById('articleSettingsBtn')?.classList.remove('active');
}

/* ===== 阅读设置 ===== */
const READING_FS_KEY = 'reading_fontsize';
const READING_THEME_KEY = 'reading_theme';

function loadReadingSettings() {
    // 字号
    const fs = localStorage.getItem(READING_FS_KEY);
    if (fs) {
        applyFontSize(parseInt(fs, 10));
    }
    // 主题
    const theme = localStorage.getItem(READING_THEME_KEY) || 'auto';
    applyTheme(theme);
}

function saveReadingSettings() {
    if (state.readingFs) localStorage.setItem(READING_FS_KEY, String(state.readingFs));
    if (state.readingTheme) localStorage.setItem(READING_THEME_KEY, state.readingTheme);
}

function applyFontSize(size) {
    state.readingFs = size;
    document.documentElement.style.setProperty('--article-fs', size + 'px');
    // 更新按钮高亮
    document.querySelectorAll('#fontSizeGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.fs, 10) === size);
    });
}

function applyTheme(theme) {
    state.readingTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    // 更新按钮高亮
    document.querySelectorAll('#themeGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
}

function toggleArticleSettings(e) {
    e?.stopPropagation();
    const panel = document.getElementById('articleSettingsPanel');
    const btn = document.getElementById('articleSettingsBtn');
    const isOpen = panel.classList.toggle('show');
    btn.classList.toggle('active', isOpen);
}

function initReadingSettingsListeners() {
    // 字号按钮
    document.querySelectorAll('#fontSizeGroup .asp-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            applyFontSize(parseInt(btn.dataset.fs, 10));
            saveReadingSettings();
        });
    });
    // 主题按钮
    document.querySelectorAll('#themeGroup .asp-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            applyTheme(btn.dataset.theme);
            saveReadingSettings();
        });
    });
    // 点击外部关闭面板（排除滚动触发的 touchstart）
    document.addEventListener('click', (e) => {
        const panel = document.getElementById('articleSettingsPanel');
        if (!panel || !panel.classList.contains('show')) return;
        // 点击面板内或 Aa 按钮时不关闭
        if (panel.contains(e.target) || e.target.id === 'articleSettingsBtn') return;
        // 点击其他按钮（如收藏、原文链接）时不关闭
        if (e.target.closest('.ap-fav-btn, .ap-original-link')) return;
        panel.classList.remove('show');
        document.getElementById('articleSettingsBtn')?.classList.remove('active');
    });
    // 滚动时不关闭面板（面板已为 fixed，会始终保持在屏幕上）
}

/* ===== 关于页面 ===== */
function showAboutPage() {
    document.body.classList.add('about-active');
    window.scrollTo(0, 0);
    if (!history.state || !history.state.about) {
        const magParam = state.currentMag;
        if (magParam) {
            history.pushState({ about: true, mag: magParam }, '', `#m=${magParam}&about`);
        } else {
            history.pushState({ about: true }, '', '#about');
        }
    }
}

function closeAboutPage() {
    document.body.classList.remove('about-active');
}

/* ===== 阅读进度环 ===== */
const RING_CIRCUMFERENCE = 2 * Math.PI * 21; // r=21
function updateReadingProgress() {
    if (!document.body.classList.contains('article-active')) return;
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const pct = docHeight > 0 ? (scrollTop / docHeight) : 0;
    // 更新进度环
    const ring = document.getElementById('progressRingFg');
    if (ring) ring.style.strokeDashoffset = RING_CIRCUMFERENCE * (1 - pct);
    // 返回顶部按钮：滚动超过 300px 时显示
    const btn = document.getElementById('backToTopBtn');
    if (btn) btn.classList.toggle('show', scrollTop > 300);
}

function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ===== Markdown 渲染 ===== */
/* 允许的 HTML 标签白名单（匹配标签名，不含 < >） */
const SAFE_TAG_NAMES = /^(div|span|p|br|strong|em|b|i|img|a|blockquote|ul|ol|li|table|tr|td|th|tbody|thead|hr|sub|sup|center|h[1-6]|figure|figcaption|font|u|s|del|ins|mark|small|big)$/i;
/* 允许的属性白名单 */
const SAFE_ATTRS = /^(style|class|src|alt|href|title|align|width|height|colspan|rowspan|target|rel|color|size|face|id)$/i;

function sanitizeHtmlTag(tag) {
    // 提取标签名
    const m = tag.match(/^<\/?([a-zA-Z0-9]+)/);
    if (!m) return escHtml(tag);
    const tagName = m[1].toLowerCase();
    if (!SAFE_TAG_NAMES.test(tagName)) return escHtml(tag);
    // 闭标签直接返回
    if (tag.startsWith('</')) return `</${tagName}>`;
    // 开标签：过滤属性
    let attrs = '';
    const attrRegex = /\s([a-zA-Z-]+)\s*=\s*"([^"]*)"/g;
    let am;
    while ((am = attrRegex.exec(tag)) !== null) {
        if (SAFE_ATTRS.test(am[1])) {
            attrs += ` ${am[1].toLowerCase()}="${am[2]}"`;
        }
    }
    const selfClose = tag.endsWith('/>') ? ' /' : '';
    return `<${tagName}${attrs}${selfClose}>`;
}

function processInlineMarkdown(text) {
    // 按HTML标签分割，保留标签
    const parts = text.split(/(<[^>]+>)/g);
    let result = '';
    for (const part of parts) {
        if (part.startsWith('<') && part.endsWith('>')) {
            result += sanitizeHtmlTag(part);
        } else {
            // 普通文本：先转义，再处理 markdown 格式
            let escaped = escHtml(part);
            // 处理图片 ![alt](url) —— 必须在链接之前处理
            escaped = escaped.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => {
                return `<img src="${url}" alt="${alt}">`;
            });
            // 处理链接 [text](url)
            escaped = escaped.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => {
                return `<a href="${url}" target="_blank" rel="noopener">${txt}</a>`;
            });
            // 先处理 **粗体**
            escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            // 再处理 *斜体*
            escaped = escaped.replace(/\*(.+?)\*/g, '<em>$1</em>');
            result += escaped;
        }
    }
    return result;
}

/* 检测中文数字标题（一、二、三、...十、十一、... + 、） */
function isChineseHeading(text) {
    // 匹配：一、二、三、...十、十一、十二、... + 、 + 后续内容
    // 或：第一章/第一节/第一部分 等
    // 或：（一）（二）（三） 开头
    return /^[一二三四五六七八九十]{1,3}、/.test(text) ||
           /^第[一二三四五六七八九十百]{1,4}[章节部分条]/.test(text);
}

function renderMarkdown(md) {
    if (!md) return '';
    // 统一换行符：CRLF/CR -> LF
    md = md.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    // 合并 3+ 连续换行为 2 个（段落分隔）
    md = md.replace(/\n{3,}/g, '\n\n');
    const paras = md.split('\n\n');
    let html = '';
    paras.forEach(p => {
        p = p.trim();
        if (!p) return;
        // Markdown 图片段落（可能被 ** 包裹）—— 作为块级元素，不包裹 <p>
        if (p.startsWith('![') || p.startsWith('**![')) {
            html += processInlineMarkdown(p);
            return;
        }
        if (p.startsWith('### ')) {
            html += '<p class="md-heading">' + processInlineMarkdown(p.substring(4)) + '</p>';
        } else if (p.startsWith('## ')) {
            html += '<p class="md-heading" style="font-size:17px;">' + processInlineMarkdown(p.substring(3)) + '</p>';
        } else if (p.startsWith('# ')) {
            html += '<p class="md-heading" style="font-size:18px;">' + processInlineMarkdown(p.substring(2)) + '</p>';
        } else if (p.startsWith('<div') || p.startsWith('<img') || p.startsWith('<table') || p.startsWith('<figure') || p.startsWith('<a ')) {
            // 块级 HTML 元素直接输出，不包裹 <p>
            html += processInlineMarkdown(p);
        } else {
            let processed = processInlineMarkdown(p);
            if (processed.startsWith('<strong>') && processed.endsWith('</strong>') &&
                processed.indexOf('<strong>') === processed.lastIndexOf('<strong>')) {
                html += '<p class="md-bold">' + processed + '</p>';
            } else if (isChineseHeading(p)) {
                // 中文数字标题（一、二、三、等）显示为小标题
                html += '<p class="md-subheading">' + processed + '</p>';
            } else {
                html += '<p>' + processed + '</p>';
            }
        }
    });
    return html;
}

/* ===== 板块视图 ===== */
function renderSections() {
    const meta = getMeta();
    const counter = {};
    meta.forEach(a => { counter[a.s] = (counter[a.s] || 0) + 1; });
    const sorted = Object.entries(counter).sort((a, b) => b[1] - a[1]);

    const container = document.getElementById('sectionContent');
    let html = '';
    sorted.forEach(([name, count]) => {
        html += `<div class="section-card" onclick="showSectionPage('${encodeURIComponent(name)}')">
            <div class="sc-name">${escHtml(name)}</div>
            <div class="sc-count">${count}<span class="sc-unit">篇</span></div>
        </div>`;
    });
    container.innerHTML = html;
}

/* ===== 板块文章页面 ===== */
function showSectionPage(encName) {
    const name = decodeURIComponent(encName);
    const meta = getMeta();
    const articles = meta.filter(a => a.s === name).sort((a, b) => b.y - a.y || a.i - b.i);

    document.getElementById('sectionPageName').textContent = name;
    document.getElementById('sectionPageCount').textContent = `${articles.length} 篇文章`;
    document.getElementById('sectionPageSearch').value = '';
    renderSectionPageBody(articles, '');

    document.body.classList.add('section-active');
    window.scrollTo(0, 0);

    const magParam = state.currentMag;
    if (!history.state || history.state.section !== encName) {
        history.pushState({ section: encName, mag: magParam }, '', `#m=${magParam}&s=${encName}`);
    }
}

function renderSectionPageBody(articles, query) {
    const body = document.getElementById('sectionPageBody');
    body.innerHTML = '';
    let filtered = articles;
    if (query) {
        const lq = query.toLowerCase();
        filtered = articles.filter(a => (a.t + ' ' + a.a).toLowerCase().includes(lq));
    }
    if (filtered.length === 0) {
        body.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-3);">未找到匹配文章</div>';
        return;
    }
    const yg = {};
    filtered.forEach(a => { if (!yg[a.y]) yg[a.y] = []; yg[a.y].push(a); });
    const years = Object.keys(yg).sort((a, b) => parseInt(b) - parseInt(a));
    let html = '';
    years.forEach(year => {
        const ya = yg[year];
        const ig = {};
        ya.forEach(a => { if (!ig[a.i]) ig[a.i] = []; ig[a.i].push(a); });
        const issues = Object.keys(ig).sort((a, b) => parseInt(b) - parseInt(a));
        html += `<div class="sp-year-group"><div class="sp-year-header">${year}年 (${ya.length}篇)</div>`;
        issues.forEach(iss => {
            const ia = ig[iss];
            const cin = parseInt(iss) <= 24 ? CN[parseInt(iss) - 1] : iss;
            html += `<div class="sp-issue-group"><div class="sp-issue-label">${cin}期</div>`;
            ia.forEach(a => {
                const author = a.a ? `<span class="author">｜${escHtml(a.a)}</span>` : '';
                const encUrl = encodeURIComponent(a.u);
                if (a.h) {
                    html += `<div class="sp-article" onclick="showArticle('${encUrl}')">${escHtml(a.t)}${author}</div>`;
                } else {
                    html += `<div class="sp-article no-body">${escHtml(a.t)}<span class="sp-no-body-tag">无全文</span>${author}</div>`;
                }
            });
            html += `</div>`;
        });
        html += `</div>`;
    });
    body.innerHTML = html;
}

function filterSectionPage() {
    const q = document.getElementById('sectionPageSearch').value.trim();
    const name = document.getElementById('sectionPageName').textContent;
    const meta = getMeta();
    const articles = meta.filter(a => a.s === name).sort((a, b) => b.y - a.y || a.i - b.i);
    renderSectionPageBody(articles, q);
}

function closeSectionPage() {
    document.body.classList.remove('section-active');
}

/* ===== 目录视图 ===== */
function renderCatalog() {
    const container = document.getElementById('catalogContent');
    if (state.catalogRendered) return;
    const meta = getMeta();
    if (meta.length === 0) {
        state.catalogPending = true;
        container.innerHTML = '<div class="loading"><div>数据加载中...</div></div>';
        return;
    }
    const catalog = {};
    meta.forEach(a => {
        if (!catalog[a.y]) catalog[a.y] = {};
        if (!catalog[a.y][a.i]) catalog[a.y][a.i] = {};
        if (!catalog[a.y][a.i][a.s]) catalog[a.y][a.i][a.s] = [];
        catalog[a.y][a.i][a.s].push(a);
    });
    state.catalogData = catalog;
    const years = Object.keys(catalog).sort((a, b) => parseInt(b) - parseInt(a));
    const chevron = svgIcon('i-chevron');
    let html = '';
    years.forEach(year => {
        const issues = Object.keys(catalog[year]).sort((a, b) => parseInt(b) - parseInt(a));
        let total = 0;
        issues.forEach(ik => total += Object.values(catalog[year][ik]).reduce((s, arr) => s + arr.length, 0));
        html += `<div class="year-block collapsed" id="yb-${year}">
            <div class="yb-header" data-year="${year}">
                <h3>${year}年</h3>
                <div class="yb-right">
                    <span class="yb-info">${issues.length}期 ｜ ${total}篇</span>
                    <span class="yb-toggle">${chevron}</span>
                </div>
            </div>
            <div class="yb-body" id="yb-body-${year}"></div>
        </div>`;
    });
    container.innerHTML = html;
    state.catalogRendered = true;

    // 事件委托：年份/期数/文章点击
    container.onclick = function(e) {
        const ybHeader = e.target.closest('.yb-header');
        if (ybHeader) {
            toggleYear(ybHeader.dataset.year);
            return;
        }
        const irHeader = e.target.closest('.ir-header');
        if (irHeader) {
            toggleIssue(irHeader.dataset.year, irHeader.dataset.issue);
            return;
        }
        const artItem = e.target.closest('.art-item');
        if (artItem) {
            showArticle(artItem.dataset.url);
            return;
        }
    };

    // 自动展开第一年
    if (years.length > 0) {
        requestAnimationFrame(() => toggleYear(years[0]));
    }
}

function toggleYear(year) {
    const block = document.getElementById(`yb-${year}`);
    if (!block) return;
    const body = document.getElementById(`yb-body-${year}`);
    const wasCollapsed = block.classList.contains('collapsed');
    block.classList.toggle('collapsed');
    if (wasCollapsed && !state.catalogExpanded.has(`y-${year}`)) {
        state.catalogExpanded.add(`y-${year}`);
        const catalog = state.catalogData;
        const issues = Object.keys(catalog[year]).sort((a, b) => parseInt(b) - parseInt(a));
        const chevron = svgIcon('i-chevron');
        let html = '';
        issues.forEach(ik => {
            const secs = catalog[year][ik];
            const secNames = Object.keys(secs);
            let issueTotal = secNames.reduce((s, sn) => s + secs[sn].length, 0);
            const cin = parseInt(ik) <= 24 ? CN[parseInt(ik) - 1] : ik;
            html += `<div class="issue-row collapsed" id="ir-${year}-${ik}">
                <div class="ir-header" data-year="${year}" data-issue="${ik}">
                    <span class="ir-title">${year}年第${cin}期</span>
                    <div class="ir-right">
                        <span class="ir-count">${issueTotal}篇</span>
                        <span class="ir-toggle">${chevron}</span>
                    </div>
                </div>
                <div class="ir-body" id="ir-body-${year}-${ik}"></div>
            </div>`;
        });
        body.innerHTML = html;
    }
}

function toggleIssue(year, ik) {
    const row = document.getElementById(`ir-${year}-${ik}`);
    if (!row) return;
    const body = document.getElementById(`ir-body-${year}-${ik}`);
    const wasCollapsed = row.classList.contains('collapsed');
    row.classList.toggle('collapsed');
    if (wasCollapsed && !state.catalogExpanded.has(`i-${year}-${ik}`)) {
        state.catalogExpanded.add(`i-${year}-${ik}`);
        const catalog = state.catalogData;
        const secs = catalog[year][ik];
        const secNames = Object.keys(secs);
        let html = '';
        secNames.forEach(sn => {
            const arts = secs[sn];
            html += `<div class="sec-group"><div class="sg-title">${escHtml(sn)} <span class="count">(${arts.length}篇)</span></div>`;
            arts.forEach(a => {
                const au = a.a ? ` <span class="ai-author">｜${escHtml(a.a)}</span>` : '';
                const encUrl = encodeURIComponent(a.u);
                html += `<div class="art-item" data-url="${encUrl}">${escHtml(a.t)}${au}</div>`;
            });
            html += `</div>`;
        });
        body.innerHTML = html;
        const ms = getMagState();
        if (ms && !ms.loadedYears.has(String(year))) loadYearData(year);
    }
}

/* ===== 收藏视图 ===== */
function renderFavorites() {
    const container = document.getElementById('favoritesContent');
    if (state.favorites.length === 0) {
        container.innerHTML = `<div class="fav-empty">
            <div class="fav-empty-icon">${svgIcon('i-bookmark')}</div>
            <div class="fav-empty-text">还没有收藏文章</div>
            <div class="fav-empty-hint">在文章详情中点击星标即可收藏</div>
        </div>`;
        return;
    }
    // 从所有已加载的杂志中查找收藏的文章
    const allMeta = [];
    for (const ms of Object.values(state.magCache)) {
        allMeta.push(...ms.meta);
    }
    const favArticles = state.favorites
        .map(url => allMeta.find(a => a.u === url))
        .filter(a => a);

    let html = `<div class="fav-header">
        <div class="fh-count">${svgIcon('i-star-fill')} 已收藏 ${favArticles.length} 篇</div>
        <div class="fh-actions">
            <button onclick="exportFavorites()">导出</button>
            <button onclick="clearFavorites()">清空</button>
        </div>
    </div>`;

    favArticles.forEach(a => {
        const ci = a.i <= 24 ? CN[a.i - 1] : a.i;
        const encUrl = encodeURIComponent(a.u);
        html += `<div class="result-card" onclick="showArticle('${encUrl}')">
            <button class="rc-fav-btn active" onclick="event.stopPropagation(); toggleFavFromCard(this, '${encUrl}')">${svgStar(true)}</button>
            <div class="rc-title">${escHtml(a.t)}</div>
            <div class="rc-meta">
                <span class="rc-tag">${a.y}年第${ci}期</span>
                <span class="rc-tag">${escHtml(a.s)}</span>
                ${a.a ? `<span class="rc-author">｜${escHtml(a.a)}</span>` : ''}
            </div>
        </div>`;
    });
    container.innerHTML = html;
}

function exportFavorites() {
    const data = JSON.stringify(state.favorites, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'djyj_favorites.json';
    a.click();
    URL.revokeObjectURL(url);
}

function clearFavorites() {
    if (!confirm('确定清空所有收藏吗？')) return;
    state.favorites = [];
    saveFavorites();
    renderFavorites();
}

/* ===== 导航 ===== */
function switchMode(mode) {
    state.currentMode = mode;
    state.isSearching = false;
    document.getElementById('searchInput').value = '';
    document.querySelectorAll('.nav-tab, .bn-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const viewMap = { section: 'sectionView', catalog: 'catalogView', favorites: 'favoritesView' };
    const view = document.getElementById(viewMap[mode]);
    if (view) view.classList.add('active');
    if (mode === 'section') renderSections();
    else if (mode === 'catalog') renderCatalog();
    else if (mode === 'favorites') renderFavorites();
    window.scrollTo(0, 0);
    requestAnimationFrame(updateStickyOffsets);
}

/* ===== 工具函数 ===== */
function escHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function highlightText(text, query) {
    if (!text || !query) return escHtml(text);
    const lt = text.toLowerCase();
    const lq = query.toLowerCase();
    let result = '';
    let lastIdx = 0;
    let idx = lt.indexOf(lq);
    while (idx >= 0) {
        result += escHtml(text.substring(lastIdx, idx));
        result += '<span class="hl">' + escHtml(text.substring(idx, idx + query.length)) + '</span>';
        lastIdx = idx + query.length;
        idx = lt.indexOf(lq, lastIdx);
    }
    result += escHtml(text.substring(lastIdx));
    return result;
}

/* ===== URL 路由解析 ===== */
function parseHash() {
    const hash = location.hash;
    if (!hash || hash === '#') return { page: 'home' };
    if (hash === '#about') return { page: 'about' };
    
    const params = new URLSearchParams(hash.substring(1));
    const mag = params.get('m');
    const articleRaw = params.get('a');
    const article = articleRaw != null ? parseInt(articleRaw, 10) : null;
    const section = params.get('s');
    const about = params.has('about');
    
    if (!mag) return { page: 'home' };
    return { page: 'magazine', mag, article, section, about };
}

/* ===== 初始化 ===== */
async function init() {
    loadFavorites();
    updateFavBadges();
    loadReadingSettings();
    initReadingSettingsListeners();

    // 导航按钮
    document.querySelectorAll('.nav-tab, .bn-item').forEach(btn => {
        btn.addEventListener('click', () => switchMode(btn.dataset.mode));
    });

    // 搜索
    const searchInput = document.getElementById('searchInput');
    document.getElementById('searchBtn').addEventListener('click', performSearch);
    searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') performSearch();
    });
    document.getElementById('bodyOnly').addEventListener('change', performSearch);
    document.querySelectorAll('input[name="searchScope"]').forEach(r => {
        r.addEventListener('change', () => {
            if (searchInput.value.trim()) performSearch();
        });
    });

    // 键盘
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            // 先关闭设置面板
            const settingsPanel = document.getElementById('articleSettingsPanel');
            if (settingsPanel?.classList.contains('show')) {
                settingsPanel.classList.remove('show');
                document.getElementById('articleSettingsBtn')?.classList.remove('active');
                return;
            }
            if (document.body.classList.contains('article-active') ||
                document.body.classList.contains('section-active') ||
                document.body.classList.contains('about-active')) {
                goBack();
            }
        }
    });

    // History API
    window.addEventListener('popstate', e => {
        if (document.body.classList.contains('article-active')) {
            closeArticlePage();
        } else if (document.body.classList.contains('section-active')) {
            closeSectionPage();
        } else if (document.body.classList.contains('about-active')) {
            closeAboutPage();
        } else if (state.currentMag && !e.state?.mag) {
            // 从杂志页返回首页
            state.currentMag = null;
            document.documentElement.style.setProperty('--mag-color-base', '#8b0000');
            document.documentElement.style.setProperty('--mag-color-dark-base', '#8b0000');
            document.body.classList.remove('mag-active');
            window.scrollTo(0, 0);
        }
    });

    // 阅读进度
    window.addEventListener('scroll', updateReadingProgress, { passive: true });

    // 窗口尺寸变化时更新 sticky 偏移量
    window.addEventListener('resize', () => {
        clearTimeout(window._resizeTimer);
        window._resizeTimer = setTimeout(updateStickyOffsets, 150);
    });

    // 加载首页计数
    loadHomeCounts();

    // URL 路由
    const route = parseHash();
    if (route.page === 'magazine' && MAGAZINES[route.mag]) {
        enterMagazine(route.mag);
        if (route.about) {
            setTimeout(() => showAboutPage(), 500);
        } else if (route.article != null) {
            // route.article 是数字索引，需要转换为 URL 后调用 showArticle
            setTimeout(() => {
                const ms = state.magCache[route.mag];
                if (ms && ms.meta[route.article]) {
                    showArticle(encodeURIComponent(ms.meta[route.article].u));
                }
            }, 600);
        } else if (route.section) {
            setTimeout(() => showSectionPage(route.section), 500);
        }
    } else if (route.page === 'about') {
        setTimeout(() => showAboutPage(), 300);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
