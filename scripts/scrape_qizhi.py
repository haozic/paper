#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从《旗帜》杂志官网按期采集目录和正文。

python scripts/scrape_qizhi.py                 # 同步官网档案页可见的全部期次
python scripts/scrape_qizhi.py 2026 6          # 重抓指定一期
python scripts/scrape_qizhi.py --check         # 只比较最新期次
python scripts/scrape_qizhi.py --authors       # 从官网文章页补齐已有目录的作者
"""

import concurrent.futures
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup, Tag

from scrape_magazines import clean_text, element_to_md, sanitize_filename

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_URL = 'https://www.qizhiwang.org.cn/GB/433029/433031/index.html'
OFFICIAL_HOST = 'www.qizhiwang.org.cn'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; PaperReader/1.0)', 'Accept-Language': 'zh-CN,zh;q=0.9'}


def official_url(url, base=ARCHIVE_URL):
    result = urljoin(base, (url or '').strip()).replace('http://www.qizhiwang.org.cn/', 'https://www.qizhiwang.org.cn/', 1)
    parsed = urlparse(result)
    if parsed.scheme != 'https' or parsed.hostname != OFFICIAL_HOST:
        raise ValueError('非《旗帜》官方网站链接: ' + result)
    return result


def fetch(url):
    url = official_url(url)
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=25, verify=False)
            official_url(response.url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            text = str(soup)
            if '\ufffd' in text:
                raise ValueError('页面出现解码替换字符: ' + url)
            return soup
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f'{url}: {last_error}')


def archive_issues():
    soup = fetch(ARCHIVE_URL)
    issues = []
    for link in soup.select('.flag-d2list .tit a[href]'):
        match = re.search(r'(20\d{2})年第(\d+)期', link.get_text(' ', strip=True))
        if match:
            issues.append((int(match.group(1)), int(match.group(2)), official_url(link['href'])))
    if not issues:
        raise RuntimeError('官网档案页没有解析到期次')
    return sorted(set(issues), reverse=True)


def issue_articles(issue_url, year, issue):
    soup = fetch(issue_url)
    expected = f'{year}年第{issue}期'
    if expected not in soup.title.get_text(' ', strip=True):
        raise RuntimeError(f'目录标题与期次不一致: {issue_url}')
    articles = []
    issue_id = re.search(r'/(\d+)/index\.html$', issue_url).group(1)
    for link in soup.select('.flag-d2list li.items > a[href], .list_14 li > a[href]'):
        url = official_url(link['href'], issue_url)
        if not re.search(r'/n1/\d{4}/\d{4}/c' + issue_id + r'-\d+\.html$', url):
            continue
        author_el = link.find('span')
        author = author_el.get_text(' ', strip=True) if author_el else ''
        title = re.sub(r'\s+', ' ', link.get_text(' ', strip=True))
        if author:
            title = re.sub(r'\s*/\s*' + re.escape(author) + r'\s*$', '', title)
        title = title.strip().rstrip('/').strip()
        if title and not any(a['u'] == url for a in articles):
            articles.append({'t': title, 'a': author, 's': '', 'y': year, 'i': issue, 'u': url, 'h': 1})
    if len(articles) < 10:
        raise RuntimeError(f'{expected} 只解析到 {len(articles)} 篇，拒绝写入')
    return articles


def article_body(article):
    soup = fetch(article['u'])
    if not article['a']:
        article['a'] = article_author(soup)
    content = soup.select_one('.flag-text-con')
    if content is None:
        raise RuntimeError('找不到正文容器: ' + article['u'])
    pieces = []
    for child in content.children:
        if not isinstance(child, Tag) or child.name in ('center', 'script', 'style'):
            continue
        if any(x in (child.get('class') or []) for x in ('editor', 'zdfy')):
            continue
        plain = child.get_text(' ', strip=True)
        if re.match(r'^[（(]?来源[：: ]*《旗帜》20\d{2}年第\d+期[）)]?$', plain):
            continue
        if child.name == 'div' and not child.find('img') and not plain:
            continue
        pieces.append(element_to_md(child, article['u']))
    body = clean_text(''.join(pieces)).strip()
    if len(body) < 40 or '\ufffd' in body or any(0x80 <= ord(ch) <= 0x9f for ch in body):
        raise RuntimeError('正文过短或包含乱码: ' + article['u'])
    return body


def article_author(soup):
    """旧期目录不带作者；文章页标题下的 pauthor 是官方作者字段。"""
    element = soup.select_one('.flag-text-tit .pauthor')
    author = re.sub(r'\s+', ' ', element.get_text(' ', strip=True)).strip() if element else ''
    author = re.sub(r'^作者\s*[：:]\s*', '', author)
    if not author:
        # 个别旧页把极短的个人署名放在副标题位；常见的“——……”仍是副标题。
        subtitle = soup.select_one('.flag-text-tit .sub')
        candidate = subtitle.get_text(' ', strip=True) if subtitle else ''
        if re.fullmatch(r'[\u4e00-\u9fff]{2,3}', candidate):
            author = candidate
    return author if len(author) <= 120 else ''


def try_article_author(article):
    try:
        return article_author(fetch(article['u'])), None
    except Exception as error:
        return '', str(error)


def try_article_body(article):
    try:
        return article_body(article), None
    except Exception as error:
        return '', str(error)


def write_json(relative, data):
    path = os.path.join(BASE_DIR, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    temporary = path + '.tmp'
    with open(temporary, 'wb') as out:
        out.write(payload)
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(.5 * (attempt + 1))


def reconcile_index():
    """恢复已写入正文和 meta、但索引写入时被中断的期次。"""
    meta_path = os.path.join(BASE_DIR, 'data/qz/meta.json')
    if not os.path.exists(meta_path):
        return
    meta = json.load(open(meta_path, encoding='utf-8'))
    index = json.load(open(os.path.join(BASE_DIR, 'data/article_index.json'), encoding='utf-8'))
    qz_index = index.setdefault('qz', {})
    by_issue = {}
    for article in meta:
        by_issue.setdefault((article['y'], article['i']), []).append(article)
    repaired = 0
    for (year, issue), articles in by_issue.items():
        for position, article in enumerate(articles, 1):
            if not article.get('h') or article['u'] in qz_index:
                continue
            name = f'{year}_{issue:02d}_{sanitize_filename(article["t"])}_{position}.md'
            relative = 'articles/qz/' + name
            if os.path.isfile(os.path.join(BASE_DIR, relative)):
                qz_index[article['u']] = relative
                repaired += 1
    if repaired:
        write_json('data/article_index.json', index)
        print(f'恢复中断前已保存的 {repaired} 篇文章索引', flush=True)


def backfill_authors(workers=4):
    meta_path = os.path.join(BASE_DIR, 'data/qz/meta.json')
    meta = json.load(open(meta_path, encoding='utf-8'))
    by_issue = {}
    for article in meta:
        if article.get('h') and not article.get('a'):
            by_issue.setdefault((article['y'], article['i']), []).append(article)
    filled = 0
    failed = 0
    for year, issue in sorted(by_issue, reverse=True):
        articles = by_issue[(year, issue)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(try_article_author, articles))
        count = 0
        for article, (author, error) in zip(articles, results):
            if author:
                article['a'] = author
                count += 1
            elif error:
                failed += 1
        filled += count
        write_json('data/qz/meta.json', meta)
        print(f'《旗帜》{year}年第{issue}期：补齐作者 {count}/{len(articles)}', flush=True)
    print(f'作者回填完成：新增 {filled}，抓取失败 {failed}，仍无作者 {sum(not a.get("a") for a in meta)}', flush=True)


def sync_issue(year, issue, issue_url, workers=4):
    articles = issue_articles(issue_url, year, issue)
    print(f'《旗帜》{year}年第{issue}期：目录 {len(articles)} 篇，抓取正文...', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(try_article_body, articles))
    failures = [(a['u'], error) for a, (_, error) in zip(articles, results) if error]
    if len(failures) > max(2, len(articles) // 10):
        raise RuntimeError(f'本期 {len(failures)}/{len(articles)} 篇正文失败，拒绝写入；示例 {failures[:2]}')
    for url, error in failures:
        print(f'  无全文 {url}: {error}', flush=True)
    shard = {}
    index_entries = {}
    for position, (article, (body, _)) in enumerate(zip(articles, results), 1):
        article['h'] = int(bool(body))
        if not body:
            continue
        filename = f'{year}_{issue:02d}_{sanitize_filename(article["t"])}_{position}.md'
        relative = 'articles/qz/' + filename
        path = os.path.join(BASE_DIR, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as out:
            out.write(body)
        shard[article['u']] = body
        index_entries[article['u']] = relative
    write_json(f'data/qz/issues/{year}-{issue}.json', shard)
    meta_path = os.path.join(BASE_DIR, 'data/qz/meta.json')
    old = json.load(open(meta_path, encoding='utf-8')) if os.path.exists(meta_path) else []
    merged = [a for a in old if (a['y'], a['i']) != (year, issue)] + articles
    merged.sort(key=lambda a: (-a['y'], -a['i']))
    write_json('data/qz/meta.json', merged)
    idx_path = os.path.join(BASE_DIR, 'data/article_index.json')
    index = json.load(open(idx_path, encoding='utf-8'))
    for article in articles:
        index.setdefault('qz', {}).pop(article['u'], None)
    index.setdefault('qz', {}).update(index_entries)
    write_json('data/article_index.json', index)
    print(f'  完成 {len(articles)} 篇，其中 {len(index_entries)} 篇有全文', flush=True)
    return len(articles)


def main():
    if '--authors' in sys.argv:
        backfill_authors()
        return
    issues = archive_issues()
    if '--check' in sys.argv:
        latest = issues[0]
        path = os.path.join(BASE_DIR, 'data/qz/meta.json')
        meta = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
        local = max(((a['y'], a['i']) for a in meta), default=None)
        print(f'《旗帜》官网最新 {latest[0]}年第{latest[1]}期；本地 {local or "无数据"}')
        return
    if len(sys.argv) >= 3:
        target = (int(sys.argv[1]), int(sys.argv[2]))
        issues = [row for row in issues if row[:2] == target]
        if not issues:
            raise SystemExit('官网档案页找不到指定期次')
    else:
        reconcile_index()
        path = os.path.join(BASE_DIR, 'data/qz/meta.json')
        existing = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
        present = {(a['y'], a['i']) for a in existing}
        issues = [row for row in issues if row[:2] not in present]
    total = 0
    for year, issue, url in sorted(issues):
        total += sync_issue(year, issue, url)
    if total:
        from scrape_magazines import write_counts
        write_counts()
        from build_search_index import main as rebuild_search_index
        rebuild_search_index()
    print(f'本次新增或更新 {len(issues)} 期、{total} 篇文章')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
