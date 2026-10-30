#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
党内刊物杂志抓取脚本
支持：求是(qs)、红旗文稿(hqwg)、党建研究(djyj)

用法：
  python scrape_magazines.py                    # 自动检测各杂志最新一期并抓取
  python scrape_magazines.py qs 2026 16         # 抓取指定期号
  python scrape_magazines.py qs 2026 16 hqwg 2026 15  # 抓取多期
  python scrape_magazines.py --covers           # 仅更新封面图
  python scrape_magazines.py --check            # 仅检查更新
"""

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from urllib.parse import urljoin, urlparse
import json
import os
import re
import sys
import time
import warnings
warnings.filterwarnings('ignore')

# ===== 配置 =====
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

# 项目根目录（脚本在 scripts/ 下）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

# 杂志配置
MAGAZINES = {
    'qs': {
        'name': '求是',
        'catalog_url': 'https://www.qstheory.cn/qs/mulu.htm',
        'meta_path': 'data/qs/meta.json',
        'issues_path': 'data/qs/issues',
        'articles_dir': 'articles/qs',
        'cover_path': 'assets/img/cover_qs.jpg',
    },
    'hqwg': {
        'name': '红旗文稿',
        'catalog_url': 'https://www.qstheory.cn/hqwglist/mulu.htm',
        'meta_path': 'data/hqwg/meta.json',
        'issues_path': 'data/hqwg/issues',
        'articles_dir': 'articles/hqwg',
        'cover_path': 'assets/img/cover_hqwg.jpg',
    },
    'djyj': {
        'name': '党建研究',
        'catalog_url': 'https://djyj.12371.cn/01/',
        'meta_path': 'data/meta.json',
        'issues_path': 'data/issues',
        'articles_dir': 'articles/djyj',
        'cover_path': 'assets/img/cover_djyj.jpg',
    },
}

# ===== 工具函数 =====
# 板块名归一化：求是/红旗文稿的目录页里，同一个板块有多种等价写法
#   '目 录'（半角空格）/ '目　录'（全角 U+3000）/ '目\xa0录'（nbsp）
# 比较板块名之前必须先去掉所有空白，否则同一个板块会被算成好几个。
_WS_RE = re.compile(r'[\s\u00a0\u3000]+')

def normalize_section(name):
    """去掉所有空白（含全角空格 / nbsp）后的板块名，用于比较。"""
    return _WS_RE.sub('', name or '')

# "目 录"是目录页自己的标题（"Table of Contents"），不是栏目，必须排除
CATALOG_HEADING = normalize_section('目 录')


def is_section_heading(span):
    """判断一个 span 是不是板块标题，是则返回标题文本，否则返回 None。

    求是/红旗文稿的目录页有两种模板：
      新模板  <span style="color: #ba372a">评论</span>
      旧模板  <font color="maroon">评论</font>
    只认前者会漏掉旧期目录页的所有板块。
    """
    style = (span.get('style') or '').replace(' ', '').lower()
    color = (span.get('color') or '').strip().lower()
    if 'ba372a' not in style and color not in ('maroon', '#ba372a'):
        return None
    text = span.get_text(strip=True)
    if not text or len(text) >= 20:
        return None
    if normalize_section(text) == CATALOG_HEADING:
        return None
    return text


def abs_url(href, base):
    """把目录页里的链接补成绝对地址。

    目录页里的文章链接是协议相对地址（//www.qstheory.cn/...），
    旧代码用 href.startswith('http') 过滤，旧期目录页会解析出 0 篇。
    """
    if not href:
        return ''
    if href.startswith('//'):
        return 'https:' + href
    if href.startswith('http'):
        return href
    return urljoin(base, href)


def canonical_article_url(url):
    """文章 URL 的规范写法：去掉 /dukan/<刊物>/<年份>/ 里的年份段。

    目录页给的链接是 /dukan/qs/2014/2020-04/16/c_x.htm，
    而 canonical 形式是 /dukan/qs/2020-04/16/c_x.htm（两者都能访问）。
    """
    return re.sub(r'(/dukan/(?:qs|hqwg)/)\d{4}/', r'\1', url or '')


def issue_path_prefix(catalog_url):
    """从目录页 URL 推出"本期文章"的路径前缀。

    旧格式 /dukan/qs/2014/2020-04/16/c_x.htm -> '/dukan/qs/2020-04/16/'
    新格式 /20251215/8b2f4ea.../c.htm           -> '/20251215/'
    用来把别期文章（目录页里常混着上一期社论的链接）排除掉。
    """
    path = urlparse(catalog_url).path
    m = re.search(r'/dukan/(?:qs|hqwg)/(?:\d{4}/)?(\d{4}-\d{2}/\d{2})/', path)
    if m:
        parts = re.match(r'(/dukan/(?:qs|hqwg)/)', path)
        return '%s%s/' % (parts.group(1), m.group(1))
    m = re.match(r'(/\d{8})/', path)
    if m:
        return m.group(1) + '/'
    return None


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.replace(' ', '')
    name = name[:60]
    return name

def clean_text(text):
    text = re.sub(r'视频代码\s*', '', text)
    text = re.sub(r'视频代码结束\s*', '', text)
    text = re.sub(r'^\s*结束\s*\n*', '', text)
    text = re.sub(r'^\s*正文页内容\s*\n*', '', text)
    text = re.sub(r'repaste\.body\.begin\s*', '', text)
    text = re.sub(r'\s*repaste\.body\.end\s*', '', text)
    text = re.sub(r'^\s*来源：《党建研究》\d+年第\d+期\s*\n*', '', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def element_to_md(element, base_url=''):
    """递归将BeautifulSoup元素转为Markdown，保留加粗、标题、段落标记等格式"""
    if element is None:
        return ''
    if isinstance(element, NavigableString):
        return str(element)
    if not isinstance(element, Tag):
        return str(element)
    name = element.name.lower() if element.name else ''

    if name in ('strong', 'b'):
        inner = ''.join(element_to_md(child, base_url) for child in element.children)
        inner = inner.strip()
        return f'**{inner}**' if inner else ''

    if name == 'img':
        src = element.get('src', '') or element.get('data-src', '') or element.get('data-original', '')
        if src and not src.startswith('http'):
            src = urljoin(base_url, src)
        alt = element.get('alt', '')
        return f'\n\n![{alt}]({src})\n\n' if src else ''

    if name == 'p':
        inner = ''.join(element_to_md(child, base_url) for child in element.children).strip()
        if not inner:
            img = element.find('img')
            return element_to_md(img, base_url) if img else ''
        style = element.get('style', '')
        is_center = 'text-align: center' in style or 'text-align:center' in style
        is_right = 'text-align: right' in style or 'text-align:right' in style
        if is_center:
            return f'<div style="text-align:center">{inner}</div>\n\n'
        elif is_right:
            return f'<div style="text-align:right">{inner}</div>\n\n'
        return f'{inner}\n\n'

    if name == 'br':
        return '\n'

    if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        level = int(name[1])
        inner = ''.join(element_to_md(child, base_url) for child in element.children).strip()
        return f'\n\n{"#" * level} {inner}\n\n'

    if name == 'a':
        return ''.join(element_to_md(child, base_url) for child in element.children)

    if name == 'div':
        style = element.get('style', '')
        inner = ''.join(element_to_md(child, base_url) for child in element.children).strip()
        if inner:
            is_center = 'text-align: center' in style or 'text-align:center' in style
            is_right = 'text-align: right' in style or 'text-align:right' in style
            if is_center:
                return f'<div style="text-align:center">{inner}</div>\n\n'
            elif is_right:
                return f'<div style="text-align:right">{inner}</div>\n\n'
            return f'{inner}\n\n'
        return ''

    return ''.join(element_to_md(child, base_url) for child in element.children)

# ===== 检查更新 =====
def get_latest_issue(mag_key):
    """从杂志网站获取最新一期号"""
    conf = MAGAZINES[mag_key]
    resp = requests.get(conf['catalog_url'], headers=HEADERS, timeout=15, verify=False)
    resp.encoding = resp.apparent_encoding
    html = resp.text

    if mag_key in ('qs', 'hqwg'):
        # 求是/红旗文稿：从目录页图片alt中提取期数
        alts = re.findall(r'alt="2026年第(\d+)期"', html)
        if alts:
            return int(alts[0])
        # 备用：从文本中提取
        issues = re.findall(r'2026年第(\d+)期', html)
        if issues:
            return max(int(x) for x in issues)
    elif mag_key == 'djyj':
        # 党建研究：从链接中提取
        links = re.findall(r'href="https?://djyj\.12371\.cn/2026/(\d+)/"', html)
        if links:
            return max(int(x) for x in links)
    return None

def get_local_latest_issue(mag_key):
    """获取本地数据中的最新一期"""
    conf = MAGAZINES[mag_key]
    meta_path = os.path.join(BASE_DIR, conf['meta_path'])
    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)
    year_issues = [(a['y'], a['i']) for a in meta]
    if not year_issues:
        return None
    return max(year_issues)


def write_counts():
    """生成 data/counts.json —— 首页只靠它显示"多少篇 / 多少期"，不用下载 meta.json。"""
    counts = {}
    for mag_key, conf in MAGAZINES.items():
        meta_path = os.path.join(BASE_DIR, conf['meta_path'])
        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        issues = set('%s-%s' % (a['y'], a['i']) for a in meta)
        counts[mag_key] = {'articles': len(meta), 'issues': len(issues)}
    out_path = os.path.join(BASE_DIR, 'data/counts.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(counts, f, ensure_ascii=False, separators=(',', ':'))
    return counts

def check_updates():
    """检查各杂志是否有更新"""
    print("=" * 60)
    print("检查杂志更新")
    print("=" * 60)
    updates = []
    for mag_key, conf in MAGAZINES.items():
        local = get_local_latest_issue(mag_key)
        latest = get_latest_issue(mag_key)
        if latest and local:
            local_year, local_issue = local
            latest_year, latest_issue = latest if isinstance(latest, tuple) else (2026, latest)
            has_update = (latest_year > local_year) or (latest_year == local_year and latest_issue > local_issue)
            status = "有更新" if has_update else "已最新"
            print(f"  {conf['name']}: 本地 {local_year}年第{local_issue}期 | 网站 {latest_year}年第{latest_issue}期 | {status}")
            if has_update:
                updates.append((mag_key, latest_year, latest_issue))
        else:
            print(f"  {conf['name']}: 获取失败")
    return updates

# ===== 目录页解析 =====
def find_catalog_url(mag_key, year, issue):
    """从杂志目录页找到指定期号的目录页URL"""
    conf = MAGAZINES[mag_key]
    resp = requests.get(conf['catalog_url'], headers=HEADERS, timeout=15, verify=False)
    resp.encoding = resp.apparent_encoding
    html = resp.text

    if mag_key in ('qs', 'hqwg'):
        # 求是/红旗文稿目录页只指向最新一期
        # 从最新期目录页（如已抓到）可通过"上一期"链接找到 19/20 期
        # 这里用 2026 年度汇总页（从 mulu.htm 的"2026年"链接获取）
        # 简化：直接返回最新期目录 URL（适合最新一期）
        links = re.findall(r'href="(https?://www\.qstheory\.cn/\d{8}/[0-9a-f]+/c\.html)"', html)
        if links:
            return links[0]
    elif mag_key == 'djyj':
        # 党建研究目录页：不带零填充（如 /2026/7/），但文章内链带零填充（如 /2026/07/22/ARTI...）
        # 两种写法都试一遍，兼容期号位数变化
        for candidate in (f'https://djyj.12371.cn/{year}/{issue}/',
                          f'https://djyj.12371.cn/{year}/{issue:02d}/'):
            try:
                r = requests.get(candidate, headers=HEADERS, timeout=15, verify=False)
                r.encoding = r.apparent_encoding
                if r.status_code == 200 and 'error.html' not in r.url and 'shtml' in r.text:
                    return candidate
            except Exception:
                continue
        return f'https://djyj.12371.cn/{year}/{issue}/'
    return None

def find_year_aggregate_url(mag_key, year):
    """从最新期目录页底部找到该年度的汇总页 URL。"""
    conf = MAGAZINES[mag_key]
    if mag_key == 'djyj':
        return f'https://djyj.12371.cn/01/'  # 党建研究使用按期次列表
    # 求是/红旗文稿：从 mulu.htm 找 "XXXX年" 链接
    resp = requests.get(conf['catalog_url'], headers=HEADERS, timeout=15, verify=False)
    resp.encoding = resp.apparent_encoding
    html = resp.text
    pattern = r'href="([^"]+)"[^>]*>\s*<img[^>]+alt="' + str(year) + r'年"'
    m = re.search(pattern, html)
    if m:
        href = m.group(1)
        if not href.startswith('http'):
            href = urljoin(conf['catalog_url'], href)
        return href
    return None

def find_issue_url_in_year(mag_key, year, issue):
    """从年度汇总页中找到指定期号的目录页 URL。"""
    conf = MAGAZINES[mag_key]
    year_url = find_year_aggregate_url(mag_key, year)
    if not year_url:
        return None
    resp = requests.get(year_url, headers=HEADERS, timeout=20, verify=False)
    resp.encoding = resp.apparent_encoding
    html = resp.text
    # 找 "2026年第N期" 文本上下文
    target = f'{year}年第{issue}期'
    # 提取所有 c.html 链接
    all_links = re.findall(r'href="(https?://www\.qstheory\.cn/\d{8}/[0-9a-f]+/c\.html)"', html)
    # 找前后有 "第N期" 文本的链接
    # 用更宽松的搜索：按"第N期"位置找其后第一个 c.html
    for m in re.finditer(re.escape(target), html):
        # 找前 400 字符内最近的 c.html
        prefix = html[max(0, m.start()-400):m.end()]
        hrefs = re.findall(r'href="(https?://www\.qstheory\.cn/\d{8}/[0-9a-f]+/c\.html)"', prefix)
        if hrefs:
            return hrefs[-1]
    return None

def parse_qs_hqwg_catalog(catalog_url, year, issue):
    """解析求是/红旗文稿目录页。

    2026-10-30 修掉的三个真 bug：
      1) 目录页里的文章链接是协议相对地址（//www.qstheory.cn/...），
         旧代码用 href.startswith('http') 过滤 → 旧期目录页解析出 0 篇；
      2) 用 f'/{year}' 过滤文章链接，会整期跳过"发布年与期号年不同"的期
         （如 2026 年第 1 期发布于 2025-12-31，URL 里根本没有 /2026）；
      3) "目 录"是目录页自己的标题（不是栏目），旧代码只按半角空格比较，
         '目　录'（全角）/'目\xa0录'（nbsp）都漏掉 → 被当成了板块，
         于是整期的文章都挂在一个叫"目 录"的假板块下面。
    """
    resp = requests.get(catalog_url, headers=HEADERS, timeout=15, verify=False)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, 'html.parser')

    content = soup.find('div', id='detailContent') or soup.find('div', class_='highlight')
    if not content:
        content = soup.find('div', class_='text')

    articles = []
    current_section = ''
    prev_article = None  # 用于合并副标题
    prefix = issue_path_prefix(catalog_url)

    if content:
        for p in content.find_all('p'):
            text = p.get_text(strip=True)
            if not text:
                continue

            # 检查是否是板块标题（红色/深红加粗文字）
            is_section = False
            for span in p.find_all('span'):
                section_text = is_section_heading(span)
                if section_text:
                    current_section = section_text
                    is_section = True
                    break
            if is_section:
                continue

            # 找文章链接
            links = p.find_all('a', href=True)
            for a in links:
                href = abs_url(a['href'], catalog_url)
                if not href.startswith('http'):
                    continue
                # 只收本期文章：路径必须落在本期目录下
                cpath = urlparse(href).path
                cpath = re.sub(r'(/dukan/(?:qs|hqwg)/)\d{4}/', r'\1', cpath)
                if prefix:
                    if not cpath.startswith(prefix):
                        continue
                elif ('/%d' % year) not in href:
                    continue
                title = a.get_text(strip=True).replace('\u3000', '').strip()
                if not title:
                    continue

                # 获取作者
                full_text = p.get_text(strip=True)
                author = ''
                if '/' in full_text:
                    parts = full_text.split('/', 1)
                    if len(parts) > 1:
                        author = parts[1].strip()

                # 副标题合并：以——开头的标题合并到前一篇文章
                if title.startswith('——') and prev_article and prev_article['url'] == href:
                    prev_article['title'] = prev_article['title'] + '——' + title
                    continue

                # 从标题中提取板块信息（│符号，新版目录页用这个带栏目）
                section = current_section
                if '│' in title:
                    parts = title.split('│', 1)
                    section = normalize_section(parts[0])
                    title = parts[1].strip()
                elif section:
                    section = normalize_section(section)

                article = {
                    'title': title,
                    'author': author,
                    'section': section,
                    'url': canonical_article_url(href),
                    'year': year,
                    'issue': issue,
                }
                articles.append(article)
                prev_article = article

    return articles

def parse_djyj_catalog(catalog_url, year, issue):
    """解析党建研究目录页"""
    resp = requests.get(catalog_url, headers=HEADERS, timeout=15, verify=False)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, 'html.parser')

    articles = []
    current_section = ''

    for el in soup.find_all(['li', 'a']):
        if el.name == 'li' and 'cur' in el.get('class', []):
            current_section = el.get_text(strip=True)
        elif el.name == 'a' and 'shtml' in (el.get('href', '') or ''):
            href = el.get('href', '')
            # 文章内链期号带零填充（/2026/07/22/...），同时兼容不带零填充的写法
            if f'/{year}/' in href and (f'/{issue:02d}/' in href or f'/{issue}/' in href):
                full_text = el.get_text(strip=True)
                if '|' in full_text:
                    parts = full_text.split('|', 1)
                    title = parts[0].strip()
                    author = parts[1].strip()
                else:
                    title = full_text
                    author = ''
                if title:
                    articles.append({
                        'title': title,
                        'author': author,
                        'section': current_section,
                        'url': href,
                        'year': year,
                        'issue': issue,
                    })
    return articles

# ===== 文章内容抓取 =====
def fetch_article_content(url, mag_type):
    """抓取文章正文内容"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')

        if mag_type in ('qs', 'hqwg'):
            content_el = soup.find('div', id='detailContent') or soup.find('div', class_='highlight')
            if not content_el:
                content_el = soup.find('div', class_='text')
        elif mag_type == 'djyj':
            content_el = soup.find('div', class_='TRS_Editor') or soup.find('div', id='font_area') or soup.find('div', class_='content')
            if not content_el:
                content_el = soup.find('div', id='detail') or soup.find('div', id='zoom')
        else:
            return ''

        if content_el:
            md = element_to_md(content_el, url)
            return clean_text(md)
        return ''
    except Exception as e:
        print(f"    抓取失败: {e}")
        return ''

# ===== 封面图下载 =====
def download_cover(mag_key, year, issue):
    """下载杂志最新一期封面图"""
    conf = MAGAZINES[mag_key]

    if mag_key in ('qs', 'hqwg'):
        # 从目录页获取封面图
        catalog_url = find_catalog_url(mag_key, year, issue)
        if not catalog_url:
            print(f"  {conf['name']}: 未找到目录页URL")
            return False
        resp = requests.get(catalog_url, headers=HEADERS, timeout=15, verify=False)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        content = soup.find('div', id='detailContent') or soup.find('div', class_='highlight')
        if content:
            img = content.find('img')
            if img:
                src = img.get('src', '') or img.get('data-src', '')
                full_url = urljoin(catalog_url, src)
                img_resp = requests.get(full_url, headers=HEADERS, timeout=30, verify=False)
                if img_resp.status_code == 200:
                    filepath = os.path.join(BASE_DIR, conf['cover_path'])
                    with open(filepath, 'wb') as f:
                        f.write(img_resp.content)
                    print(f"  {conf['name']}: 封面图已更新 ({len(img_resp.content)} bytes)")
                    return True
    elif mag_key == 'djyj':
        # 党建研究：从目录页找2026年的图片
        catalog_url = f'https://djyj.12371.cn/{year}/{issue}/'
        resp = requests.get(catalog_url, headers=HEADERS, timeout=15, verify=False)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        for img in soup.find_all('img'):
            src = img.get('src', '') or img.get('data-src', '')
            full_url = urljoin(catalog_url, src)
            if str(year) in full_url:
                img_resp = requests.get(full_url, headers=HEADERS, timeout=30, verify=False)
                if img_resp.status_code == 200:
                    filepath = os.path.join(BASE_DIR, conf['cover_path'])
                    with open(filepath, 'wb') as f:
                        f.write(img_resp.content)
                    print(f"  {conf['name']}: 封面图已更新 ({len(img_resp.content)} bytes)")
                    return True
    print(f"  {conf['name']}: 封面图下载失败")
    return False

# ===== 主流程 =====
def process_magazine(mag_key, year, issue):
    """处理一个杂志的完整抓取流程"""
    conf = MAGAZINES[mag_key]
    print(f"\n{'='*60}")
    print(f"开始处理: {conf['name']} {year}年第{issue}期")
    print(f"{'='*60}")

    # 找到目录页URL
    catalog_url = find_catalog_url(mag_key, year, issue)
    # 求是/红旗文稿：mulu.htm 只返回最新期，需要从年度汇总页里找目标期
    if mag_key in ('qs', 'hqwg') and year == 2026 and issue < get_latest_issue(mag_key):
        issue_url = find_issue_url_in_year(mag_key, year, issue)
        if issue_url:
            catalog_url = issue_url
            print(f"  找到目标期目录: {issue_url}")
    if not catalog_url:
        print("  !! 未找到目录页URL")
        return []

    # 解析目录页
    if mag_key in ('qs', 'hqwg'):
        articles = parse_qs_hqwg_catalog(catalog_url, year, issue)
    else:
        articles = parse_djyj_catalog(catalog_url, year, issue)

    print(f"目录页解析到 {len(articles)} 篇文章")
    if not articles:
        print("  !! 未解析到文章")
        return []

    # 逐篇抓取
    results = []
    for i, art in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {art['title'][:40]}...")
        content = fetch_article_content(art['url'], mag_key)
        has_full = 1 if content and len(content) > 50 else 0

        # 保存markdown文件
        safe_title = sanitize_filename(art['title'])
        file_prefix = f'{year}_{issue:02d}'
        filename = f'{file_prefix}_{safe_title}.md'
        art_dir = os.path.join(BASE_DIR, conf['articles_dir'])
        filepath = os.path.join(art_dir, filename)

        if os.path.exists(filepath):
            filename = f'{file_prefix}_{safe_title}_{i}.md'
            filepath = os.path.join(art_dir, filename)

        rel_path = f'articles/{mag_key}/{filename}'

        if has_full:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

        results.append({
            'meta': {
                't': art['title'], 'a': art['author'], 's': art['section'],
                'y': year, 'i': issue, 'u': art['url'], 'h': has_full,
            },
            'content': content if has_full else '',
            'rel_path': rel_path if has_full else None,
            'url': art['url'],
        })
        time.sleep(0.5)

    # 更新meta.json
    meta_path = os.path.join(BASE_DIR, conf['meta_path'])
    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)
    for r in results:
        meta.append(r['meta'])
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))

    # 更新该期的正文分片：data/<mag>/issues/<年>-<期>.json
    issue_path = os.path.join(BASE_DIR, conf['issues_path'], f'{year}-{issue}.json')
    os.makedirs(os.path.dirname(issue_path), exist_ok=True)
    if os.path.exists(issue_path):
        with open(issue_path, encoding='utf-8') as f:
            shard = json.load(f)
    else:
        shard = {}
    for r in results:
        if r['content']:
            shard[r['url']] = r['content']
    with open(issue_path, 'w', encoding='utf-8') as f:
        json.dump(shard, f, ensure_ascii=False, separators=(',', ':'))

    # 更新article_index.json
    idx_path = os.path.join(BASE_DIR, 'data/article_index.json')
    with open(idx_path, encoding='utf-8') as f:
        idx = json.load(f)
    if mag_key not in idx:
        idx[mag_key] = {}
    for r in results:
        if r['rel_path']:
            idx[mag_key][r['url']] = r['rel_path']
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, separators=(',', ':'))

    # 刷新首页计数（data/counts.json）
    write_counts()

    print(f"\n  完成: {len(results)}篇 ({sum(1 for r in results if r['content'])}篇有全文)")
    print(f"  正文分片: {conf['issues_path']}/{year}-{issue}.json")
    return results

def main():
    args = sys.argv[1:]

    if '--check' in args:
        check_updates()
        return

    if '--covers' in args:
        print("下载最新封面图...")
        for mag_key in MAGAZINES:
            local = get_local_latest_issue(mag_key)
            if local:
                download_cover(mag_key, local[0], local[1])
        return

    if '--counts' in args:
        # 只重建首页计数文件，不联网
        counts = write_counts()
        print("已重建 data/counts.json：")
        for k, v in counts.items():
            print(f"  {k}: {v['articles']} 篇 / {v['issues']} 期")
        return

    # 解析命令行参数：杂志 年份 期号
    tasks = []
    i = 0
    while i < len(args):
        mag = args[i]
        if mag not in MAGAZINES:
            print(f"未知杂志: {mag}（可选: qs, hqwg, djyj）")
            return
        year = int(args[i+1]) if i+1 < len(args) else 2026
        issue = int(args[i+2]) if i+2 < len(args) else None
        if issue is None:
            # 自动检测最新期号
            latest = get_latest_issue(mag)
            if latest:
                issue = latest if isinstance(latest, int) else latest[1]
            else:
                print(f"  无法获取 {MAGAZINES[mag]['name']} 最新期号")
                return
        tasks.append((mag, year, issue))
        i += 3

    if not tasks:
        # 自动检测所有杂志更新
        print("自动检测更新...")
        updates = check_updates()
        if not updates:
            print("\n所有杂志均已最新，无需更新。")
            return
        tasks = updates

    # 执行抓取
    all_results = {}
    for mag_key, year, issue in tasks:
        results = process_magazine(mag_key, year, issue)
        all_results[mag_key] = results
        # 下载封面图
        download_cover(mag_key, year, issue)

    # 汇总
    print(f"\n{'='*60}")
    print("汇总")
    print(f"{'='*60}")
    for mag_key, results in all_results.items():
        name = MAGAZINES[mag_key]['name']
        total = len(results)
        with_full = sum(1 for r in results if r['content'])
        print(f"  {name}: {total}篇 ({with_full}篇有全文)")

if __name__ == '__main__':
    main()
