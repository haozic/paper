#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 meta.json 中 URL 丢失的条目。

背景
----
《党建研究》目录页里，部分板块（如"贯彻落实全国组织部长会议精神""全国党建工作座谈会发言摘登"）
只列出标题和作者，**不提供单篇文章链接**（纯 <span> 文本）。早期版本的解析器把这类条目也写进了
meta.json，导致 `u`（URL）字段为空字符串。

后果：
  1. 前端 `meta.findIndex(a => a.u === url)` 用空串匹配 —— 点任何一条都打开**第一条**坏记录，
     打开的是错文章；
  2. 这些条目污染搜索结果、板块统计和文章总数；
  3. 站点上表现为"点得动、打不开"的死链。

修复思路
--------
这类文章在官网确实没有单篇页面，但**该期目录页（TOC）里能看到它的标题、作者和板块**。
因此把 `u` 赋成「该期目录页 + 标题片段」：

    https://djyj.12371.cn/2026/2/#持续加强党的创新理论武装

  - 地址唯一 → 点开就是正确的那一篇（标题/作者/期号/板块都对）
  - "原文链接"指向真实的目录页，用户可去官网核对
  - 仍保持 h=0（无全文），阅读页会诚实提示"该文章无全文内容"

每条赋值前都会先抓取目录页并**校验该标题确实出现在页面中**，校验不通过的不赋值。

用法
----
  python scripts/repair_empty_urls.py            # 预览（默认，不写文件）
  python scripts/repair_empty_urls.py --apply    # 写回
  python scripts/repair_empty_urls.py --apply --drop-unmatched   # 匹配不到的条目直接删除
"""

import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape_magazines import (  # noqa: E402
    MAGAZINES,
    BASE_DIR,
    HEADERS,
    find_catalog_url,
)

import requests  # noqa: E402


def normalize_title(t):
    """标题归一化：保留中文与字母数字，去掉标点空白，用作 URL 片段与匹配键"""
    if not t:
        return ''
    t = unicodedata.normalize('NFKC', t)
    return ''.join(ch.lower() for ch in t if ch.isalnum() or '\u4e00' <= ch <= '\u9fff')


def strip_spaces(text):
    """去掉 HTML 标签与所有空白字符（含全角空格），用于"页面上确实列着这个标题"的宽松校验。

    目录页里一个条目可能是 <b>主标题</b><br><b>副标题</b>，而 meta 里存的是拼在一起的文本，
    所以必须先剥标签再比对。
    """
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = unicodedata.normalize('NFKC', text)
    return ''.join(ch for ch in text if not ch.isspace())


def load_json(path):
    full = os.path.join(BASE_DIR, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(os.path.join(BASE_DIR, path), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def fetch_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        resp.encoding = resp.apparent_encoding
        if resp.status_code != 200 or 'error.html' in resp.url:
            return None
        return resp.text
    except Exception:
        return None


def issue_toc_url(mag_key, year, issue):
    """该期目录页 URL。党建研究为 /年/期/（不补零），求是/红旗文稿走脚本内的查找逻辑。"""
    if mag_key == 'djyj':
        for cand in (f'https://djyj.12371.cn/{year}/{issue}/',
                     f'https://djyj.12371.cn/{year}/{issue:02d}/'):
            html = fetch_page(cand)
            if html:
                return cand, html
        return None, None
    url = find_catalog_url(mag_key, year, issue)
    if not url:
        return None, None
    return url, fetch_page(url)


def main():
    apply = '--apply' in sys.argv
    drop_unmatched = '--drop-unmatched' in sys.argv

    print('=' * 70)
    print('修复空 URL 条目' + ('' if apply else '（预览模式，加 --apply 才会写回）'))
    print('=' * 70)

    stats = {'fixed': 0, 'dropped': 0, 'unmatched': 0}

    for mag_key, conf in MAGAZINES.items():
        meta = load_json(conf['meta_path'])
        if meta is None:
            continue
        broken = [a for a in meta if not a.get('u')]
        if not broken:
            print(f'\n[{mag_key}] {conf["name"]}: 无空 URL 条目')
            continue

        issues = sorted({(a['y'], a['i']) for a in broken})
        print(f'\n[{mag_key}] {conf["name"]}: {len(broken)} 条空 URL，涉及 {len(issues)} 期')
        used_urls = set()

        for year, issue in issues:
            entries = [a for a in broken if a['y'] == year and a['i'] == issue]
            toc_url, html = issue_toc_url(mag_key, year, issue)
            if not toc_url or not html:
                print(f'  {year}年第{issue:02d}期: 目录页不可达，跳过 {len(entries)} 条')
                stats['unmatched'] += len(entries)
                continue

            fixed_here = 0
            unmatched = []
            page_text = strip_spaces(html)
            for ent in entries:
                title = ent.get('t') or ''
                # 目录页 HTML 里标题可能是多空格/换行分隔，这里忽略空白再比对
                if title and strip_spaces(title) in page_text:
                    slug = normalize_title(title)[:60] or 'x'
                    u = f'{toc_url}#{slug}'
                    n = 2
                    while u in used_urls:
                        u = f'{toc_url}#{slug}-{n}'
                        n += 1
                    used_urls.add(u)
                    ent['u'] = u
                    fixed_here += 1
                else:
                    unmatched.append(ent)

            stats['fixed'] += fixed_here
            stats['unmatched'] += len(unmatched)
            print(f'  {year}年第{issue:02d}期: 目录页 {toc_url}')
            print(f'      修复 {fixed_here} 条'
                  + (f'，未匹配 {len(unmatched)} 条' if unmatched else ''))

            if apply and drop_unmatched and unmatched:
                drop_titles = {(e.get('t'), e.get('a')) for e in unmatched}
                before = len(meta)
                meta[:] = [a for a in meta
                           if not (not a.get('u')
                                   and (a.get('t'), a.get('a')) in drop_titles
                                   and a['y'] == year and a['i'] == issue)]
                stats['dropped'] += before - len(meta)
                print(f'      已删除 {before - len(meta)} 条匹配不到的记录')

        if apply:
            save_json(conf['meta_path'], meta)
            print(f'  [{mag_key}] {conf["name"]} meta.json 已更新')

    print('\n' + '=' * 70)
    print(f'修复 {stats["fixed"]} 条   删除 {stats["dropped"]} 条   未匹配 {stats["unmatched"]} 条')
    if not apply:
        print('这是预览，未写入任何文件。确认无误后加 --apply 重跑。')


if __name__ == '__main__':
    main()
