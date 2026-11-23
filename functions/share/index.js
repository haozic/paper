const MAGAZINES = {
  qs: { name: '求是', meta: '/data/qs/meta.json', cover: '/assets/img/cover_qs.jpg' },
  hqwg: { name: '红旗文稿', meta: '/data/hqwg/meta.json', cover: '/assets/img/cover_hqwg.jpg' },
  djyj: { name: '党建研究', meta: '/data/meta.json', cover: '/assets/img/cover_djyj.jpg' },
  qz: { name: '旗帜', meta: '/data/qz/meta.json', cover: '/assets/img/cover_qz_2026_06.jpg' }
};

const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[char]);

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const mag = url.searchParams.get('m');
  const source = url.searchParams.get('u');
  const config = MAGAZINES[mag];
  if (!config || !source || source.length > 2048) return new Response('Invalid article', { status: 400 });

  let articles;
  try {
    const response = await env.ASSETS.fetch(new URL(config.meta, url));
    if (!response.ok) throw new Error('Article index unavailable');
    articles = await response.json();
  } catch (_) { return new Response('Article index unavailable', { status: 503 }); }

  const index = articles.findIndex(item => item.u === source);
  if (index < 0) return new Response('Article not found', { status: 404 });
  const article = articles[index];
  const title = escapeHtml(article.t);
  const description = escapeHtml(`${config.name} · ${article.y}年第${article.i}期`);
  const shareUrl = escapeHtml(url.href);
  const imageUrl = escapeHtml(new URL(config.cover, url).href);
  const readerUrl = new URL('/', url);
  readerUrl.hash = `m=${mag}&a=${index}`;

  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><meta name="description" content="${description}"><meta property="og:type" content="article"><meta property="og:title" content="${title}"><meta property="og:description" content="${description}"><meta property="og:url" content="${shareUrl}"><meta property="og:image" content="${imageUrl}"><meta name="twitter:card" content="summary"><meta name="twitter:title" content="${title}"><link rel="canonical" href="${shareUrl}"><script>location.replace(${JSON.stringify(readerUrl.href)})</script></head><body><a href="${escapeHtml(readerUrl.href)}">阅读《${title}》</a></body></html>`;
  return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=3600', 'X-Content-Type-Options': 'nosniff' } });
}
