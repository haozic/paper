'use strict';

/* ===== 全局缓存版本号（与 index.html 一致，用于 data 目录下的 json 缓存破坏） ===== */
const DATA_VERSION = (typeof window !== 'undefined' && window.__DATA_VERSION__) || '20261030d';
function dataUrl(p) { return p + (p.includes('?') ? '&' : '?') + 'v=' + DATA_VERSION; }

/* ===== 杂志配置 ===== */
const MAGAZINES = {
    qs: {
        name: '求是',
        fullName: '《求是》',
        color: '#8b0000',
        colorDark: '#8b0000',
        dataPath: 'data/qs',
        issuesPath: 'data/qs/issues',
        source: 'https://www.qstheory.cn/qs/mulu.htm',
        desc: '中共中央委员会机关刊',
    },
    hqwg: {
        name: '红旗文稿',
        fullName: '《红旗文稿》',
        color: '#8b0000',
        colorDark: '#8b0000',
        dataPath: 'data/hqwg',
        issuesPath: 'data/hqwg/issues',
        source: 'https://www.qstheory.cn/hqwglist/mulu.htm',
        desc: '政治理论半月刊',
    },
    djyj: {
        name: '党建研究',
        fullName: '《党建研究》',
        color: '#8b0000',
        colorDark: '#8b0000',
        dataPath: 'data',
        issuesPath: 'data/issues',
        source: 'https://djyj.12371.cn/',
        desc: '党建理论与实践研究月刊',
    },
};

/* ===== 状态管理 ===== */
const state = {
    currentMag: null,       // null=首页, 'qs'|'hqwg'|'djyj'
    magCache: {},           // {qs: {meta, bodyText, loadedIssues, fullTextReady}, ...}
    favorites: [],
    currentMode: 'section',
    currentArticleUrl: null,
    fullTextReady: false,
    catalogRendered: false,
    catalogPending: false,
    catalogExpanded: new Set(),
    isSearching: false,
    searchResults: [],
    searchToken: 0,         // 递增令牌：查询词变化时让旧的正文搜索立即作废
    lastQuery: '',         // 最近一次已提交的搜索词
    currentPage: 1,
    pageSize: 20,
    readingFs: 20,          // 文章字号
    readingTheme: 'auto',   // light / dark / auto
    readingLh: '2.05',      // 行距
    readingW: '0',          // 页宽偏移（px）
    readingIndent: '2',     // 首行缩进（em）
    readingPaper: 'default', // 纸张：default / warm / white
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
/* 正文按"期"分片加载，合并到扁平的 bodyText（URL → 正文）里，
   这样无论哪一期加载完，都能 O(1) 取到任意文章的正文。 */
function newMagState() {
    return {
        meta: [],
        bodyText: {},              // URL → 正文（扁平）
        loadedIssues: new Set(),   // 已加载的期次 "<年>-<期>"
        loadingIssues: new Set(),  // 正在加载的期次
        fullTextReady: false,      // 该刊全部期次是否都已加载完
        articleIndex: null,
        indexLoaded: false,
    };
}

function getMagState() {
    if (!state.currentMag) return null;
    if (!state.magCache[state.currentMag]) {
        state.magCache[state.currentMag] = newMagState();
    }
    return state.magCache[state.currentMag];
}

function getMeta() { var ms = getMagState(); return ms ? (ms.meta || []) : []; }

/* ===== 首页：加载各杂志计数 ===== */
/* 只取一个几十字节的 counts.json，不再为了三个数字下载 1.3 MB 的 meta.json */
async function loadHomeCounts() {
    let counts = null;
    try {
        const resp = await fetch(dataUrl('data/counts.json'));
        if (resp.ok) counts = await resp.json();
    } catch (e) {
        console.warn('counts.json 加载失败，回退到 meta.json 统计:', e);
    }
    if (counts) {
        for (const [key, c] of Object.entries(counts)) {
            const countEl = document.getElementById(`${key}Count`);
            const issuesEl = document.getElementById(`${key}Issues`);
            if (countEl) countEl.textContent = c.articles;
            if (issuesEl) issuesEl.textContent = c.issues;
        }
        return;
    }
    // 回退：老版本没有 counts.json 时仍能显示计数
    for (const [key, conf] of Object.entries(MAGAZINES)) {
        try {
            const resp = await fetch(dataUrl(`${conf.dataPath}/meta.json`));
            const meta = await resp.json();
            const countEl = document.getElementById(`${key}Count`);
            const issuesEl = document.getElementById(`${key}Issues`);
            if (countEl) countEl.textContent = meta.length;
            if (issuesEl) {
                issuesEl.textContent = [...new Set(meta.map(a => `${a.y}-${a.i}`))].length;
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

/* 按需加载某本杂志的 meta.json（首页不再预加载，收藏页/跨杂志跳转时才用） */
async function loadMagMeta(magKey) {
    if (!state.magCache[magKey]) state.magCache[magKey] = newMagState();
    const ms = state.magCache[magKey];
    if (ms.meta.length > 0) return ms.meta;
    const conf = MAGAZINES[magKey];
    if (!conf) return [];
    try {
        const resp = await fetch(dataUrl(`${conf.dataPath}/meta.json`));
        ms.meta = await resp.json();
    } catch (e) {
        console.error(`加载 ${magKey} 元数据失败:`, e);
    }
    return ms.meta;
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
    onMagazineDataReady();
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
/* 加载某一期的正文分片：data/<mag>/issues/<年>-<期>.json
   单片约 200 KB（旧方案是整年 4~18 MB），合并进 ms.bodyText 扁平表。 */
async function loadIssueData(year, issue, retry = 2) {
    const ms = getMagState();
    if (!ms) return false;
    const conf = MAGAZINES[state.currentMag];
    if (!conf) return false;
    const key = year + '-' + issue;
    if (ms.loadedIssues.has(key)) return true;
    if (ms.loadingIssues.has(key)) return false;     // 已在加载中，不重复发起
    ms.loadingIssues.add(key);
    let resp = null;
    try {
        resp = await fetch(dataUrl(`${conf.issuesPath}/${key}.json`));
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const obj = await resp.json();
        for (const u in obj) ms.bodyText[u] = obj[u];
        ms.loadedIssues.add(key);
        return true;
    } catch (e) {
        // 整期无正文（如党建研究 2024 年第 8 期）会返回 404，属正常情况，不重试；
        // 网络中断 / 5xx 属临时故障，退避 800ms 后重试。
        if (retry > 0 && (!resp || resp.status !== 404)) {
            await new Promise(r => setTimeout(r, 800));
            ms.loadingIssues.delete(key);
            return loadIssueData(year, issue, retry - 1);
        }
        ms.loadedIssues.add(key);        // 标记为已处理，避免反复重试
        return false;
    } finally {
        ms.loadingIssues.delete(key);
    }
}

/* 列出某本杂志所有"有正文"的期次（按最新在前） */
function listBodyIssues(ms) {
    const seen = new Set();
    const list = [];
    for (const a of ms.meta) {
        if (!a.h) continue;
        const key = a.y + '-' + a.i;
        if (seen.has(key)) continue;
        seen.add(key);
        list.push({ y: a.y, i: a.i, key: key });
    }
    list.sort((x, y) => (y.y - x.y) || (y.i - x.i));
    return list;
}

function onMagazineDataReady() {
    const ms = getMagState();
    if (!ms) return;
    const status = document.getElementById('searchStatus');
    status.className = 'search-status ready';
    status.textContent = '标题搜索就绪 · 正文搜索按需加载';

    // 正文不再预加载：搜索时按期增量加载
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

/* 同步搜索范围按钮的选中态。
   Chrome 69 不支持 CSS :has()，需要用 .checked 类兜底；
   现代浏览器同时保留 :has() 规则，两者结果一致。 */
function syncScopeChecked() {
    document.querySelectorAll('.scope-option').forEach(opt => {
        const input = opt.querySelector('input[name="searchScope"]');
        if (input && input.checked) opt.classList.add('checked');
        else opt.classList.remove('checked');
    });
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

    // 记住本次查询词，供 Esc 失焦还原
    state.lastQuery = input.value;
    // 使上一次尚未结束的正文搜索失效
    state.searchToken++;

    const scope = getSearchScope();
    const bo = document.getElementById('bodyOnly').checked;

    // 标题搜索：立即执行
    let results;
    if (scope === 'title') {
        results = collectMatches(ms, query, scope, bo);
    } else {
        // 正文相关范围：先给出当前已加载正文能命中的结果，再按期增量补全
        results = collectMatches(ms, query, scope, bo);
        if (!ms.fullTextReady) {
            performBodySearch(query, results, scope, bo, state.searchToken);
            return;
        }
    }

    finishSearch(results, query, scope, input);
}

/* 单篇文章是否命中查询 */
function articleMatches(a, query, scope, ms) {
    if (scope === 'title' || scope === 'all') {
        const metaData = (a.t + ' ' + a.a + ' ' + a.s).toLowerCase();
        if (metaData.includes(query)) return true;
    }
    if ((scope === 'body' || scope === 'all') && a.h) {
        const body = ms.bodyText[a.u];
        if (body && body.toLowerCase().includes(query)) return true;
    }
    return false;
}

/* 按已加载的正文收集命中结果 */
function collectMatches(ms, query, scope, bo) {
    return ms.meta.filter(a => {
        if (bo && !a.h) return false;
        return articleMatches(a, query, scope, ms);
    });
}

/* 正文搜索：按"期"增量加载，每批加载完立刻刷新结果，而不是等全部下载完 */
async function performBodySearch(query, initialResults, scope, bo, token) {
    const ms = getMagState();
    if (!ms) return;
    const input = document.getElementById('searchInput');
    const infoEl = document.getElementById('resultInfo');

    // 先显示标题搜索结果，不让学生等
    if (initialResults && initialResults.length > 0) {
        state.searchResults = initialResults;
        state.currentPage = 1;
        const qDisplay = input.value.trim();
        infoEl.textContent = `共 ${initialResults.length} 篇（标题匹配）· 正在按期加载正文搜索更多...`;
        renderSearchPage();
    } else {
        infoEl.textContent = '正在按期加载正文用于搜索...';
        document.getElementById('searchResults').innerHTML = '<div class="loading"><div class="spinner"></div><div>加载正文数据中...</div></div>';
    }

    const issues = listBodyIssues(ms);
    const BATCH = 6;          // 每批并发的期次数
    const qDisplay = input.value.trim();
    const scopeLabel = scope === 'all' ? '标题+正文' : '仅正文';
    let done = 0;

    for (let k = 0; k < issues.length; k += BATCH) {
        if (state.searchToken !== token) return;      // 查询词已变，放弃这次搜索
        const batch = issues.slice(k, k + BATCH);
        await Promise.all(batch.map(it => loadIssueData(it.y, it.i)));
        // 等这一批的工夫里，用户可能已经改了关键词 / 换了范围 / 切了视图。
        // 慢网下这一等可达数秒，不重新校验就会把过期结果写回界面
        // （已用反向对照实测：撤掉本行会让"仅标题"被旧搜索覆盖成"仅正文"）。
        if (state.searchToken !== token) return;
        done += batch.length;

        // 每批加载完立刻用最新的正文重新匹配并刷新结果
        const results = collectMatches(ms, query, scope, bo);
        state.searchResults = results;
        infoEl.textContent = `共 ${results.length} 篇文章（关键词："${qDisplay}" ｜ 范围：${scopeLabel}） · 正文已加载 ${done}/${issues.length} 期`;
        renderSearchPage();
    }

    if (state.searchToken !== token) return;
    ms.fullTextReady = true;
    state.fullTextReady = true;
    document.getElementById('searchStatus').textContent = '全文搜索就绪';
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
                const body = ms.bodyText[a.u] || '';
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
/* replaceHist=true 时用 replaceState 改写当前历史条目（上一/下一篇切换用，避免后退键逐篇回溯） */
async function showArticle(encUrl, replaceHist) {
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
    showContinueBanner(url);
    renderArticleFooter(url, a);

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
        const st = { articleUrl: url, mag: magKey };
        if (replaceHist && history.state && history.state.articleUrl) {
            history.replaceState(st, '', `#m=${magKey}&a=${idx}`);
        } else {
            history.pushState(st, '', `#m=${magKey}&a=${idx}`);
        }
    }

    if (!a.h) {
        bodyEl.innerHTML = '<div class="no-body">该文章无全文内容<br><small>可能为新闻汇总条目或专刊文献</small></div>';
        return;
    }

    bodyEl.innerHTML = '<div class="article-loading"><div class="spinner"></div><div>加载正文...</div></div>';

    // 优先从 markdown 文件加载（轻量，单文件按需加载）
    const mdPath = ms.articleIndex ? ms.articleIndex[url] : undefined;
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

    // 回退到该期的正文分片（文章没有 markdown 备份时）
    if (!ms.loadedIssues.has(a.y + '-' + a.i)) {
        const ok = await loadIssueData(a.y, a.i);
        if (!ok && !ms.bodyText[url]) {
            bodyEl.innerHTML = `<div class="no-body">正文数据加载失败<br>
                <small>可能是网络不稳定，请重试</small><br>
                <button class="retry-btn" onclick="retryShowArticle('${encUrl}')">重新加载</button></div>`;
            return;
        }
    }

    renderArticleBody(url, bodyEl);
}

function updateArticleMeta(a, wordCount) {
    const ci = a.i <= 24 ? CN[a.i - 1] : a.i;
    let meta = `${a.y}年第${ci}期 ｜ ${escHtml(a.s)}${a.a ? ' ｜ ' + escHtml(a.a) : ''}`;
    if (wordCount > 0) {
        meta += ` ｜ 约 ${wordCount} 字`;
        // 按 400 字/分钟估算阅读时长
        const mins = Math.max(1, Math.round(wordCount / 400));
        meta += ` ｜ 约 ${mins} 分钟`;
    }
    document.getElementById('articleMeta').innerHTML = meta;
}

function countWords(text) {
    if (!text) return 0;
    return text.replace(/\s/g, '').length;
}

function renderArticleBody(url, bodyEl) {
    const ms = getMagState();
    if (!ms) return;
    const text = ms.bodyText[url];
    if (text) {
        const body = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
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
    const mdPath = ms.articleIndex ? ms.articleIndex[url] : undefined;
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

    // 回退到该期的正文分片
    ms.loadedIssues.delete(a.y + '-' + a.i);
    const ok = await loadIssueData(a.y, a.i);
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
    // 关闭前先记录当前阅读位置（此时页面仍在 article-active 状态，滚动高度有效）
    if (document.body.classList.contains('article-active')) {
        const url = state.currentArticleUrl;
        if (url) {
            const max = document.documentElement.scrollHeight - window.innerHeight;
            const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
            saveReadPosition(url, ratio);
        }
    }
    document.body.classList.remove('article-active');
    state.currentArticleUrl = null;
    const ring = document.getElementById('progressRingFg');
    if (ring) ring.style.strokeDashoffset = RING_CIRCUMFERENCE;
    var btt = document.getElementById('backToTopBtn');
    if (btt) btt.classList.remove('show');
    // 关闭设置面板
    var sp = document.getElementById('articleSettingsPanel');
    if (sp) sp.classList.remove('show');
    var sb = document.getElementById('articleSettingsBtn');
    if (sb) sb.classList.remove('active');
    // 隐藏"继续阅读"提示条与文末导航（下次进入文章时再按需显示）
    var banner = document.getElementById('articleContinue');
    if (banner) banner.hidden = true;
    var footer = document.getElementById('articleFooter');
    if (footer) footer.hidden = true;
    var rel = document.getElementById('articleRelated');
    if (rel) rel.hidden = true;
}

/* ===== 阅读设置 ===== */
const READING_FS_KEY = 'reading_fontsize';
const READING_THEME_KEY = 'reading_theme';
const READING_LH_KEY = 'reading_lineheight';
const READING_W_KEY = 'reading_width';
const READING_INDENT_KEY = 'reading_indent';
const READING_PAPER_KEY = 'reading_paper';

/* 纸张配色：仅浅色模式有意义，深色模式下自动失效 */
const PAPER_PRESETS = {
    default: null,
    warm: {
        bg: '#f3ecd7', bg2: '#ece2c6', card: '#f7f2e0', text: '#3b3429',
        text2: '#756b58', text3: '#9a8f78', border: '#ded3b6', border2: '#d0c3a0'
    },
    white: {
        bg: '#ffffff', bg2: '#f7f7f7', card: '#ffffff', text: '#2b2726',
        text2: '#66605e', text3: '#918a88', border: '#e9e9e9', border2: '#dcdcdc'
    }
};

function loadReadingSettings() {
    // 字号
    const fs = localStorage.getItem(READING_FS_KEY);
    if (fs) {
        applyFontSize(parseInt(fs, 10));
    }
    // 主题（会顺带重算纸张配色）
    const theme = localStorage.getItem(READING_THEME_KEY) || 'auto';
    applyTheme(theme);
    // 行距
    const lh = localStorage.getItem(READING_LH_KEY);
    if (lh) applyLineHeight(lh);
    // 页宽
    const w = localStorage.getItem(READING_W_KEY);
    if (w !== null && w !== '') applyWidth(w);
    // 首行缩进
    const ind = localStorage.getItem(READING_INDENT_KEY);
    if (ind !== null && ind !== '') applyIndent(ind);
    // 纸张
    applyPaper(localStorage.getItem(READING_PAPER_KEY) || 'default');
}

function saveReadingSettings() {
    if (state.readingFs) localStorage.setItem(READING_FS_KEY, String(state.readingFs));
    if (state.readingTheme) localStorage.setItem(READING_THEME_KEY, state.readingTheme);
    if (state.readingLh) localStorage.setItem(READING_LH_KEY, String(state.readingLh));
    if (state.readingW !== null && state.readingW !== undefined) localStorage.setItem(READING_W_KEY, String(state.readingW));
    if (state.readingIndent !== null && state.readingIndent !== undefined) localStorage.setItem(READING_INDENT_KEY, String(state.readingIndent));
    if (state.readingPaper) localStorage.setItem(READING_PAPER_KEY, state.readingPaper);
}

function applyFontSize(size) {
    state.readingFs = size;
    document.documentElement.style.setProperty('--article-fs', size + 'px');
    // 更新按钮高亮
    document.querySelectorAll('#fontSizeGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.fs, 10) === size);
    });
}

function applyLineHeight(lh) {
    state.readingLh = String(lh);
    document.documentElement.style.setProperty('--article-lh', String(lh));
    document.querySelectorAll('#lineHeightGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', parseFloat(btn.dataset.lh) === parseFloat(lh));
    });
}

function applyWidth(delta) {
    state.readingW = String(delta);
    document.documentElement.style.setProperty('--article-w-delta', String(delta) + 'px');
    document.querySelectorAll('#widthGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.w, 10) === parseInt(delta, 10));
    });
}

function applyIndent(em) {
    state.readingIndent = String(em);
    document.documentElement.style.setProperty('--article-indent', String(em) + 'em');
    document.querySelectorAll('#indentGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.indent, 10) === parseInt(em, 10));
    });
}

/* 当前是否为深色（含"跟随系统"时的系统偏好） */
function isDarkTheme() {
    const t = state.readingTheme || 'auto';
    if (t === 'dark') return true;
    if (t === 'light') return false;
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

/* 纸张底色：作用在文章页自身的 CSS 变量上，深色模式下不生效 */
function applyPaper(name) {
    state.readingPaper = name;
    const page = document.getElementById('articlePage');
    const preset = PAPER_PRESETS[name];
    const props = ['--bg', '--bg-2', '--card', '--text', '--text-2', '--text-3', '--border', '--border-2'];
    if (page) {
        if (!preset || isDarkTheme()) {
            props.forEach(p => page.style.removeProperty(p));
        } else {
            page.style.setProperty('--bg', preset.bg);
            page.style.setProperty('--bg-2', preset.bg2);
            page.style.setProperty('--card', preset.card);
            page.style.setProperty('--text', preset.text);
            page.style.setProperty('--text-2', preset.text2);
            page.style.setProperty('--text-3', preset.text3);
            page.style.setProperty('--border', preset.border);
            page.style.setProperty('--border-2', preset.border2);
        }
    }
    document.querySelectorAll('#paperGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.paper === name);
    });
}

function applyTheme(theme) {
    state.readingTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    // 更新按钮高亮
    document.querySelectorAll('#themeGroup .asp-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
    // 主题变了，纸张配色要重算（深色下不生效）
    applyPaper(state.readingPaper || 'default');
}

function toggleArticleSettings(e) {
    if (e && e.stopPropagation) e.stopPropagation();
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
    // 行距按钮
    document.querySelectorAll('#lineHeightGroup .asp-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            applyLineHeight(btn.dataset.lh);
            saveReadingSettings();
        });
    });
    // 页宽按钮
    document.querySelectorAll('#widthGroup .asp-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            applyWidth(btn.dataset.w);
            saveReadingSettings();
        });
    });
    // 首行缩进按钮
    document.querySelectorAll('#indentGroup .asp-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            applyIndent(btn.dataset.indent);
            saveReadingSettings();
        });
    });
    // 纸张按钮
    document.querySelectorAll('#paperGroup .asp-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            applyPaper(btn.dataset.paper);
            saveReadingSettings();
        });
    });
    // 系统主题变化时，纸张配色跟着重算
    if (window.matchMedia) {
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const onSchemeChange = () => {
            if ((state.readingTheme || 'auto') === 'auto') applyPaper(state.readingPaper || 'default');
        };
        if (mq.addEventListener) mq.addEventListener('change', onSchemeChange);
        else if (mq.addListener) mq.addListener(onSchemeChange);
    }
    // 点击外部关闭面板（排除滚动触发的 touchstart）
    document.addEventListener('click', (e) => {
        const panel = document.getElementById('articleSettingsPanel');
        if (!panel || !panel.classList.contains('show')) return;
        // 点击面板内或 Aa 按钮时不关闭
        if (panel.contains(e.target) || e.target.id === 'articleSettingsBtn') return;
        // 点击其他按钮（如收藏、原文链接）时不关闭
        if (e.target.closest('.ap-fav-btn, .ap-original-link, .ap-copy-btn')) return;
        panel.classList.remove('show');
        var asb = document.getElementById('articleSettingsBtn');
        if (asb) asb.classList.remove('active');
    });
    // 滚动时不关闭面板（面板已为 fixed，会始终保持在屏幕上）
}

/* ===== 阅读位置记忆 ===== */
const READ_POS_KEY = 'reading_position';
const READ_POS_MAX = 60;      // 最多保留最近 60 篇的阅读位置
let _lastPosSaveAt = 0;

function getReadPositions() {
    try {
        const raw = localStorage.getItem(READ_POS_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
}

function saveReadPosition(url, ratio) {
    if (!url) return;
    try {
        const all = getReadPositions();
        all[url] = { r: Math.round(ratio * 1000) / 1000, t: Date.now() };
        const keys = Object.keys(all);
        if (keys.length > READ_POS_MAX) {
            keys.sort(function (a, b) { return (all[b].t || 0) - (all[a].t || 0); });
            for (let i = READ_POS_MAX; i < keys.length; i++) delete all[keys[i]];
        }
        localStorage.setItem(READ_POS_KEY, JSON.stringify(all));
    } catch (e) { /* 隐私模式等场景忽略 */ }
}

function getReadPosition(url) {
    const all = getReadPositions();
    const v = all[url];
    if (!v) return 0;
    return typeof v === 'number' ? v : (v.r || 0);
}

/* 滚动时按 1.5 秒节流记录进度 */
function maybeSaveReadPosition() {
    if (!document.body.classList.contains('article-active')) return;
    const now = Date.now();
    if (now - _lastPosSaveAt < 1500) return;
    _lastPosSaveAt = now;
    const url = state.currentArticleUrl;
    if (!url) return;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    saveReadPosition(url, ratio);
}

function showContinueBanner(url) {
    const banner = document.getElementById('articleContinue');
    if (!banner) return;
    const ratio = getReadPosition(url);
    if (ratio > 0.15 && ratio < 0.9) {
        const pct = document.getElementById('articleContinuePct');
        if (pct) pct.textContent = Math.round(ratio * 100) + '%';
        banner.hidden = false;
    } else {
        banner.hidden = true;
    }
}

function continueReading() {
    const url = state.currentArticleUrl;
    if (!url) return;
    const ratio = getReadPosition(url);
    const banner = document.getElementById('articleContinue');
    if (banner) banner.hidden = true;
    const go = function () {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        if (max > 0) window.scrollTo({ top: Math.round(max * ratio), behavior: 'smooth' });
    };
    go();
    // 正文可能还在异步加载，稍后按最终高度再校正一次
    setTimeout(go, 700);
}

function dismissContinue() {
    const banner = document.getElementById('articleContinue');
    if (banner) banner.hidden = true;
}

/* ===== 上下篇 / 相关阅读 ===== */

/* 按（年, 期, 抓取顺序）排好序的文章列表 */
function getOrderedMeta() {
    const ms = getMagState();
    if (!ms) return [];
    if (!ms._ordered || ms._orderedLen !== ms.meta.length) {
        const arr = ms.meta.map(function (a, i) { return { a: a, i: i }; });
        arr.sort(function (x, y) {
            if (x.a.y !== y.a.y) return x.a.y - y.a.y;
            if (x.a.i !== y.a.i) return x.a.i - y.a.i;
            return x.i - y.i;
        });
        ms._ordered = arr;
        ms._orderedLen = ms.meta.length;
    }
    return ms._ordered;
}

function issueLabel(a) {
    const ci = (a.i >= 1 && a.i <= 24) ? CN[a.i - 1] : a.i;
    return a.y + '年第' + ci + '期';
}

/* 取当前文章的上一篇 / 下一篇（供文末导航与键盘 ←/→ 共用） */
function getArticleNeighbours(url) {
    const ms = getMagState();
    if (!ms) return { prev: null, next: null, pos: -1, ordered: [] };
    const ordered = getOrderedMeta();
    let pos = -1;
    for (let i = 0; i < ordered.length; i++) {
        if (ordered[i].a.u === url) { pos = i; break; }
    }
    const prev = pos > 0 ? ordered[pos - 1].a : null;
    const next = (pos >= 0 && pos < ordered.length - 1) ? ordered[pos + 1].a : null;
    return { prev: prev, next: next, pos: pos, ordered: ordered };
}

function renderArticleFooter(url, cur) {
    const ms = getMagState();
    const footer = document.getElementById('articleFooter');
    const navEl = document.getElementById('articleNav');
    if (!ms || !footer || !navEl) return;

    const nb = getArticleNeighbours(url);
    const ordered = nb.ordered;
    const pos = nb.pos;
    const prev = nb.prev;
    const next = nb.next;

    let html = '';
    if (prev) {
        html += '<button class="ap-nav-item" data-url="' + encodeURIComponent(prev.u) + '">' +
            '<span class="ap-nav-dir"><svg class="icon"><use href="#i-arrow-left"/></svg>上一篇 · ' + issueLabel(prev) + '</span>' +
            '<span class="ap-nav-title">' + escHtml(prev.t) + '</span></button>';
    } else {
        html += '<div class="ap-nav-empty"></div>';
    }
    if (next) {
        html += '<button class="ap-nav-item" data-url="' + encodeURIComponent(next.u) + '">' +
            '<span class="ap-nav-dir">下一篇 · ' + issueLabel(next) + '<svg class="icon"><use href="#i-arrow-right"/></svg></span>' +
            '<span class="ap-nav-title">' + escHtml(next.t) + '</span></button>';
    } else {
        html += '<div class="ap-nav-empty"></div>';
    }
    navEl.innerHTML = html;

    navEl.querySelectorAll('.ap-nav-item[data-url]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            showArticle(btn.getAttribute('data-url'), true);
        });
    });

    renderRelatedArticles(cur, pos, ordered);

    footer.hidden = false;
}

function renderRelatedArticles(cur, pos, ordered) {
    const relEl = document.getElementById('articleRelated');
    if (!relEl || !cur) { if (relEl) relEl.hidden = true; return; }

    const sameSec = [];
    const sameAuthor = [];
    for (let i = 0; i < ordered.length; i++) {
        const a = ordered[i].a;
        if (a.u === cur.u) continue;
        const d = Math.abs(i - pos);
        if (a.s && cur.s && a.s === cur.s) sameSec.push({ a: a, d: d });
        else if (cur.a && a.a === cur.a) sameAuthor.push({ a: a, d: d });
    }
    sameSec.sort(function (x, y) { return x.d - y.d; });
    sameAuthor.sort(function (x, y) { return x.d - y.d; });

    const picks = sameSec.slice(0, 5);
    for (let i = 0; i < sameAuthor.length && picks.length < 5; i++) {
        if (picks.every(function (p) { return p.a.u !== sameAuthor[i].a.u; })) picks.push(sameAuthor[i]);
    }
    if (picks.length === 0) { relEl.hidden = true; return; }

    let html = '<div class="ap-related-title">相关阅读</div><div class="ap-related-list">';
    picks.forEach(function (x) {
        html += '<div class="ap-related-item" data-url="' + encodeURIComponent(x.a.u) + '">' +
            '<span class="ap-related-meta">' + issueLabel(x.a) + '</span>' +
            '<span class="ap-related-name">' + escHtml(x.a.t) + '</span></div>';
    });
    html += '</div>';
    relEl.innerHTML = html;
    relEl.hidden = false;

    relEl.querySelectorAll('.ap-related-item[data-url]').forEach(function (item) {
        item.addEventListener('click', function () {
            showArticle(item.getAttribute('data-url'), true);
        });
    });
}

/* ===== 复制链接 ===== */
function copyArticleLink() {
    const btn = document.getElementById('articleCopyBtn');
    const url = window.location.href;
    const done = function () {
        if (!btn) return;
        btn.classList.add('copied');
        btn.innerHTML = '<svg class="icon"><use href="#i-check"/></svg>';
        setTimeout(function () {
            btn.classList.remove('copied');
            btn.innerHTML = '<svg class="icon"><use href="#i-link"/></svg>';
        }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done).catch(function () { fallbackCopyText(url, done); });
    } else {
        fallbackCopyText(url, done);
    }
}

/* 非安全上下文（http）或老浏览器下的复制兜底 */
function fallbackCopyText(text, cb) {
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', 'readonly');
        ta.style.position = 'fixed';
        ta.style.top = '-1000px';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        ta.setSelectionRange(0, text.length);
        document.execCommand('copy');
        document.body.removeChild(ta);
        if (cb) cb();
    } catch (e) { /* 复制失败则静默 */ }
}

/* ===== 快捷键：/ 与 Ctrl/⌘+K 聚焦搜索 ===== */
function focusSearch() {
    if (!state.currentMag) return;                    // 首页没有搜索框
    const input = document.getElementById('searchInput');
    if (!input) return;
    const inOverlay = document.body.classList.contains('article-active') ||
        document.body.classList.contains('section-active') ||
        document.body.classList.contains('about-active');
    if (inOverlay) {
        goBack();                                    // 先退回杂志视图
        setTimeout(function () {
            const i = document.getElementById('searchInput');
            if (i) { i.focus(); i.select(); }
        }, 150);
        return;
    }
    input.focus();
    input.select();
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
    // 记录阅读位置（内部按 1.5 秒节流）
    maybeSaveReadPosition();
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
        // 不再预加载整年正文：文章页优先读单篇 markdown，
        // 万一缺失时按需加载"该期"分片即可（约 200 KB）。
    }
}

/* ===== 收藏视图 ===== */
/* 收藏可能来自任意一本杂志，而首页现在只加载 counts.json（不再预载三本 meta.json），
   所以这里在真正需要时才把对应杂志的 meta.json 补齐。 */
async function renderFavorites() {
    const container = document.getElementById('favoritesContent');
    if (state.favorites.length === 0) {
        container.innerHTML = `<div class="fav-empty">
            <div class="fav-empty-icon">${svgIcon('i-bookmark')}</div>
            <div class="fav-empty-text">还没有收藏文章</div>
            <div class="fav-empty-hint">在文章详情中点击星标即可收藏</div>
        </div>`;
        return;
    }

    const collect = function () {
        const allMeta = [];
        for (const ms of Object.values(state.magCache)) allMeta.push(...ms.meta);
        return state.favorites.map(url => allMeta.find(a => a.u === url)).filter(a => a);
    };

    let favArticles = collect();
    if (favArticles.length < state.favorites.length) {
        // 还有收藏没解析出来 —— 把三本杂志的 meta.json 补上
        container.innerHTML = '<div class="loading"><div class="spinner"></div><div>正在加载收藏列表...</div></div>';
        await Promise.all(Object.keys(MAGAZINES).map(k => loadMagMeta(k)));
        favArticles = collect();
    }

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
    state.searchToken++;                 // 取消尚未结束的正文搜索
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
/* ===== PWA：Service Worker / 离线提示 / 新版本提示（P2-1） ===== */
function updateOnlineStatus() {
    if (navigator.onLine) document.body.classList.remove('is-offline');
    else document.body.classList.add('is-offline');
}

/* 离线状态监听放在顶层：密码门阶段就该提示离线，而不是等进入系统后 */
window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
updateOnlineStatus();

function showUpdateToast() {
    const toast = document.getElementById('updateToast');
    if (!toast || toast.classList.contains('show')) return;
    toast.classList.add('show');
    toast.addEventListener('click', () => { location.reload(); }, { once: true });
}

function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    // Service Worker 仅在安全上下文可用（https 或 localhost）
    const host = location.hostname;
    const secure = location.protocol === 'https:' ||
        host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    if (!secure) return;

    // 用版本号注册：版本一变就装上新的 Service Worker，由它清掉旧缓存，
    // 保证不会把上一期的 meta / 索引当新数据用（版本常量与 index.html 共用同一个）
    navigator.serviceWorker.register('sw.js?v=' + DATA_VERSION).then(reg => {
        reg.addEventListener('updatefound', () => {
            const sw = reg.installing;
            if (!sw) return;
            sw.addEventListener('statechange', () => {
                // 已有旧 SW 在控制页面、且新 SW 装好 → 提示用户刷新
                if (sw.state === 'installed' && navigator.serviceWorker.controller) {
                    showUpdateToast();
                }
            });
        });
    }).catch(e => {
        console.warn('Service Worker 注册失败：', e);
    });
}

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
            syncScopeChecked();
            if (searchInput.value.trim()) performSearch();
        });
    });
    // Chrome 69 不支持 :has()，用 .checked 类同步搜索范围选中态
    syncScopeChecked();

    // "继续阅读"按钮
    const continueBtn = document.getElementById('articleContinueBtn');
    if (continueBtn) continueBtn.addEventListener('click', continueReading);

    // 键盘
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            // 先关闭设置面板
            const settingsPanel = document.getElementById('articleSettingsPanel');
            if (settingsPanel && settingsPanel.classList.contains('show')) {
                settingsPanel.classList.remove('show');
                var asb2 = document.getElementById('articleSettingsBtn');
                if (asb2) asb2.classList.remove('active');
                return;
            }
            // 搜索框内按 Esc：失焦并还原为上次已提交的查询词
            const si = document.getElementById('searchInput');
            if (si && document.activeElement === si) {
                si.blur();
                si.value = state.lastQuery || '';
                return;
            }
            if (document.body.classList.contains('article-active') ||
                document.body.classList.contains('section-active') ||
                document.body.classList.contains('about-active')) {
                goBack();
            }
            return;
        }

        // 输入状态下不劫持快捷键
        const t = e.target;
        const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
            t.tagName === 'SELECT' || t.isContentEditable);

        // Ctrl/⌘ + K：聚焦搜索框
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            focusSearch();
            return;
        }
        if (typing) return;

        // "/"：聚焦搜索框
        if (e.key === '/') {
            e.preventDefault();
            focusSearch();
            return;
        }

        // 文章页 ← / →（或 J / K）：上一篇 / 下一篇
        const panelOpen = document.getElementById('articleSettingsPanel');
        if (document.body.classList.contains('article-active') &&
            !(panelOpen && panelOpen.classList.contains('show')) &&
            (e.key === 'ArrowLeft' || e.key === 'ArrowRight' ||
             e.key === 'j' || e.key === 'J' || e.key === 'k' || e.key === 'K')) {
            const nb = getArticleNeighbours(state.currentArticleUrl);
            const isPrev = (e.key === 'ArrowLeft' || e.key === 'j' || e.key === 'J');
            const target = isPrev ? nb.prev : nb.next;
            if (target) {
                e.preventDefault();
                showArticle(encodeURIComponent(target.u), true);
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
        } else if (state.currentMag && !(e.state && e.state.mag)) {
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

    // 注册 Service Worker（离线阅读）
    registerServiceWorker();

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

// 暴露给密码门模块：登录通过后再启动主应用
window.__app_init__ = init;

/* ===== 访问密码门（必须在 init 前通过） ===== */
(function() {
    'use strict';

    var STORAGE_KEY = 'djyj_gate_ok';
    var STORAGE_TS = 'djyj_gate_ts';
    var PASSWORD = '5255';
    // 默认 12 小时有效期；设为 0 表示关闭会话过期
    var TTL_MS = 12 * 60 * 60 * 1000;

    function isAuthed() {
        try {
            var ok = localStorage.getItem(STORAGE_KEY) === '1';
            if (!ok) return false;
            if (TTL_MS <= 0) return true;
            var ts = parseInt(localStorage.getItem(STORAGE_TS) || '0', 10);
            if (!ts) return false;
            return (Date.now() - ts) < TTL_MS;
        } catch (e) {
            return false;
        }
    }

    function setAuthed() {
        try {
            localStorage.setItem(STORAGE_KEY, '1');
            localStorage.setItem(STORAGE_TS, String(Date.now()));
        } catch (e) {}
    }

    function openGate() {
        var gate = document.getElementById('gate');
        if (gate) gate.classList.remove('gate--hidden');
        setTimeout(function() {
            var input = document.getElementById('gateInput');
            if (input) input.focus();
        }, 200);
        // 锁定背景滚动
        document.body.classList.add('gate-active');
    }

    function closeGate() {
        var gate = document.getElementById('gate');
        if (gate) gate.classList.add('gate--hidden');
        document.body.classList.remove('gate-active');
    }

    function shake(el) {
        if (!el) return;
        el.classList.remove('gate-shake');
        // 强制 reflow 触发动画
        void el.offsetWidth;
        el.classList.add('gate-shake');
    }

    function showHint(text, ok) {
        var hint = document.getElementById('gateHint');
        if (!hint) return;
        hint.textContent = text;
        hint.className = 'gate-hint' + (ok ? ' gate-hint--ok' : ' gate-hint--err');
    }

    function bind() {
        var form = document.getElementById('gateForm');
        var input = document.getElementById('gateInput');
        var toggle = document.getElementById('gateToggle');
        var wrap = document.getElementById('gateInputWrap');
        if (!form || !input) return;

        // 切换显示/隐藏密码
        if (toggle) {
            toggle.addEventListener('click', function() {
                if (input.type === 'password') {
                    input.type = 'text';
                    toggle.setAttribute('aria-label', '隐藏密码');
                    toggle.title = '隐藏密码';
                } else {
                    input.type = 'password';
                    toggle.setAttribute('aria-label', '显示密码');
                    toggle.title = '显示密码';
                }
                input.focus();
            });
        }

        // 输入时清空错误提示
        input.addEventListener('input', function() {
            if (input.classList.contains('gate-input--err')) {
                input.classList.remove('gate-input--err');
                showHint('', false);
            }
        });

        // 提交验证
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var val = input.value;
            if (val === PASSWORD) {
                setAuthed();
                input.classList.remove('gate-input--err');
                showHint('验证成功，正在进入...', true);
                setTimeout(closeGate, 300);
            } else {
                input.classList.add('gate-input--err');
                shake(wrap);
                showHint('密码错误，请重试', false);
                input.select();
            }
        });
    }

    function init() {
        if (isAuthed()) {
            // 已登录：直接隐藏
            var gate = document.getElementById('gate');
            if (gate) gate.classList.add('gate--hidden');
            document.body.classList.remove('gate-active');
            return;
        }
        bind();
        openGate();
    }

    // 把 init() 调用包在密码门之后
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            init();
            // 触发真正的应用 init
            if (typeof window.__app_init__ === 'function') window.__app_init__();
        });
    } else {
        init();
        if (typeof window.__app_init__ === 'function') window.__app_init__();
    }
})();
