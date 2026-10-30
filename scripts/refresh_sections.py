#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按期刷新板块名（只抓目录页，不重下正文）。

为什么需要这个脚本
------------------
2026-10-30 用户发现"板块页有空白板块和重复板块"，追查下去发现数据层的老问题：
求是 / 红旗文稿共 4500 余篇文章里，有 4500 余条（准确说：求是 2587 条、红旗文稿
2019 条）的板块名是 **"目 录"** —— 这不是求是真实的栏目，而是抓取脚本的兜底值：

    1) 旧版目录页模板用 <font color="maroon">评论</font> 标栏目，
       解析器只认 <span style="color: #ba372a">，旧期目录页解析不出栏目；
    2) "目 录"是目录页自己的标题（Table of Contents），被当成了板块，
       于是整期的文章都挂在一个叫"目 录"的假板块下面。

求是网后来把旧期目录页的栏目标题和文章页的"栏目"字段都下线了，
所以那 158 期的栏目信息在**来源站已经不可得**；但 2025 年 15 期起的新目录页
用「标题│栏目」的形式标了专栏，这部分可以刷回来。

本脚本做的事
------------
    1. 逐期抓目录页（每期 1 个请求，比重抓正文轻得多：正文有 85 MB）；
    2. 从目录页解析出每篇文章的板块，按 URL 写回 meta.json 的 s 字段；
    3. 把"目 录"这种兜底名清空（它不是栏目，留着会让人误以为求是有个叫
       "目 录"的栏目）；
    4. 报告：刷回多少条、还有多少条确实没有栏目信息。

用法
----
    python -u scripts/refresh_sections.py              # 预演（默认，不写盘）
    python -u scripts/refresh_sections.py --apply      # 实际写回 meta.json
    python -u scripts/refresh_sections.py --mag qs     # 只处理某一本
    python -u scripts/refresh_sections.py --issues 2025-24,2026-1   # 只处理指定期
"""

import argparse
import json
import os
import re
import sys
import time
import warnings
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')   # verify=False 的 InsecureRequestWarning 噪音太大

# 直接复用抓取脚本里的解析规则，避免两处逻辑漂移
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_magazines import (      # noqa: E402
    HEADERS as SCRAPE_HEADERS,
    abs_url,
    is_section_heading,
    normalize_section as scrape_normalize_section,
)
from canonical_sections import canonical    # noqa: E402  板块名归一表（改名合并）

HEADERS = SCRAPE_HEADERS

sys.stdout.reconfigure(encoding='utf-8', errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

MAGAZINES = {
    'qs': {
        'name': '求是',
        'catalog_url': 'https://www.qstheory.cn/qs/mulu.htm',
        'meta_path': 'data/qs/meta.json',
    },
    'hqwg': {
        'name': '红旗文稿',
        'catalog_url': 'https://www.qstheory.cn/hqwglist/mulu.htm',
        'meta_path': 'data/hqwg/meta.json',
    },
}

# 兜底板块名（不是真实栏目）：归一化后等于"目录"的都要清掉
PLACEHOLDER = '目录'

WS_RE = re.compile(r'[\s\u00a0\u3000]+')


def normalize_section(name):
    """去掉所有空白（含全角空格 / nbsp）后的板块名，用于比较。"""
    return scrape_normalize_section(name)


def url_key(u):
    """URL 匹配键：忽略协议、忽略 /dukan/<刊物>/<年份>/ 的年份段。"""
    u = re.sub(r'(/dukan/(?:qs|hqwg)/)\d{4}/', r'\1', u or '')
    u = re.sub(r'^https?://', '', u)
    return u.lower()


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
            r.encoding = r.apparent_encoding
            if r.status_code == 200:
                return r.text
            last = 'HTTP %s' % r.status_code
        except Exception as e:      # 网络抖动重试
            last = str(e)
        time.sleep(0.8 * (i + 1))
    return None


def issue_catalog_urls(mag_key):
    """从 mulu.htm → 年份页 → 每期目录页，逐级取出每期的目录页地址。

    返回 {'2020-8': 'https://...', ...}
    """
    conf = MAGAZINES[mag_key]
    root = conf['catalog_url']
    html = fetch(root)
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')

    years = {}
    for a in soup.find_all('a', href=True):
        m = re.fullmatch(r'(\d{4})年', a.get_text(strip=True))
        if m:
            years[m.group(1)] = urljoin(root, a['href'])
    if not years:
        return {}

    name = conf['name']
    out = {}
    for y, yurl in sorted(years.items()):
        yhtml = fetch(yurl)
        if not yhtml:
            continue
        ysoup = BeautifulSoup(yhtml, 'html.parser')
        for a in ysoup.find_all('a', href=True):
            m = re.fullmatch(r'《%s》%s年第(\d+)期' % (name, y), a.get_text(strip=True))
            if m:
                out['%s-%s' % (y, int(m.group(1)))] = urljoin(yurl, a['href'])
    return out


def parse_sections(catalog_url):
    """解析目录页，返回 {url_key: 板块名}。

    只返回**能确定**板块名的文章 —— 判定规则与抓取脚本一致：
      1) 标题里带「│」的（新版目录页用这个标专栏）；
      2) 出现在红色栏目标题之后的（红旗文稿的目录页用这个标栏目）。

    关键：**「│」只标在每一栏的第一篇上，同栏的后续文章继承这个栏目**
    （求是 2026 年第 15 期实测：第 16 篇「文化中国│…」之后连续 9 篇都属
    于"文化中国"）。漏掉继承会把真实栏目大面积清空。

    两种机制都认不到的，说明来源站根本没给这篇文章标栏目，
    就不写进结果（由调用方清空旧值）。
    """
    html = fetch(catalog_url)
    if not html:
        return None      # 抓不到就整期不动，别拿猜测去覆盖已有数据
    soup = BeautifulSoup(html, 'html.parser')
    content = (soup.find('div', id='detailContent')
               or soup.find('div', class_='highlight')
               or soup.find('div', class_='text'))
    if not content:
        return {}

    out = {}
    current = ''
    known = False
    for p in content.find_all('p'):
        heading = None
        for span in p.find_all('span'):
            heading = is_section_heading(span)
            if heading:
                break
        if heading:
            current = canonical(heading)
            known = True
            continue
        for a in p.find_all('a', href=True):
            href = abs_url(a['href'], catalog_url)
            if not href.startswith('http'):
                continue
            title = a.get_text(strip=True).replace('　', '').strip()
            if not title:
                continue
            if '│' in title:
                section = canonical(normalize_section(title.split('│', 1)[0]))
                if section and section != PLACEHOLDER:
                    current = section
                    known = True
                    out[url_key(href)] = current
                continue
            if known and current:
                out[url_key(href)] = current
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='实际写回 meta.json（默认只预演）')
    ap.add_argument('--mag', help='只处理某一本（qs / hqwg）')
    ap.add_argument('--issues', help='只处理指定期，逗号分隔，如 2025-24,2026-1')
    args = ap.parse_args()

    mags = [args.mag] if args.mag else list(MAGAZINES)
    only = None
    if args.issues:
        only = set(x.strip() for x in args.issues.split(',') if x.strip())

    print('=' * 72)
    print('刷新板块名（只抓目录页，不重下正文）')
    print('模式：%s' % ('实际写盘' if args.apply else '预演（加 --apply 才写）'))
    print('=' * 72)

    for mag_key in mags:
        conf = MAGAZINES[mag_key]
        print('\n[%s] %s' % (mag_key, conf['name']))
        pages = issue_catalog_urls(mag_key)
        if only:
            pages = {k: v for k, v in pages.items() if k in only}
        print('  找到 %d 期的目录页' % len(pages))

        # 逐期抓目录页，汇总 url -> 板块（并记下哪些期成功抓到了）
        found = {}
        ok_issues = set()
        failed = []
        for n, (issue, url) in enumerate(sorted(pages.items()), 1):
            secs = parse_sections(url)
            if secs is None:
                failed.append(issue)
                continue
            ok_issues.add(issue)
            found.update(secs)
            if n % 20 == 0:
                print('    已抓 %d/%d 期，暂得 %d 条带栏目文章'
                      % (n, len(pages), len(found)))
                sys.stdout.flush()

        meta_path = os.path.join(BASE_DIR, conf['meta_path'])
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)

        updated = 0
        cleared = 0
        kept = 0
        skipped = 0
        dist_before = {}
        for a in meta:
            k = normalize_section(a.get('s') or '')
            dist_before[k] = dist_before.get(k, 0) + 1
        for a in meta:
            issue = '%d-%d' % (a['y'], a['i'])
            if issue not in ok_issues:
                skipped += 1        # 这一期的目录页没抓到，别拿猜测覆盖已有数据
                continue
            key = url_key(a.get('u') or '')
            verified = found.get(key)
            if verified:
                if verified != (a.get('s') or ''):
                    a['s'] = verified
                    updated += 1
                else:
                    kept += 1
            else:
                # 来源站没能证实这个板块名 → 清空。
                # 之前留在数据里的"目 录"是抓取脚本的兜底值（不是求是真栏目），
                # "评论"是老版本把微博分享控件 <span class="big">评论</span>
                # 当成了栏目 —— 两者都是假板块名，一并清掉。
                if (a.get('s') or ''):
                    a['s'] = ''
                    cleared += 1
                else:
                    kept += 1

        dist_after = {}
        for a in meta:
            k = normalize_section(a.get('s') or '')
            dist_after[k] = dist_after.get(k, 0) + 1

        print('  板块名刷新：%d 条（来源站目录页能证实）' % updated)
        print('  假板块名清空：%d 条（"目 录"兜底值 / "评论"微博控件产物）' % cleared)
        print('  保持原样：%d 条' % kept)
        if skipped:
            print('  目录页没抓到、本期未处理：%d 条' % skipped)
        print('  目录页没给出栏目信息的期：%d 期（%s%s）'
              % (len(failed), ', '.join(failed[:6]), ' ...' if len(failed) > 6 else ''))
        print('  板块分布（前→后）：')
        for k in sorted(set(dist_before) | set(dist_after)):
            b = dist_before.get(k, 0)
            a_ = dist_after.get(k, 0)
            if b != a_ or a_:
                print('     %-24s %5d → %5d' % (repr(k) if k else '(空/未分栏目)', b, a_))

        if args.apply:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, separators=(',', ':'))
            print('  已写回 %s' % conf['meta_path'])
        else:
            print('  （预演，未写盘）')


if __name__ == '__main__':
    main()
