# -*- coding: utf-8 -*-
"""重建正文数据：years/<year>.json → issues/<year>-<issue>.json（按期分片）

背景
----
1. `data/<mag>/years/<year>.json` 单文件 4~18 MB，正文搜索必须整年整年地下；
   党建研究 2026 年的文件更是达到 18.5 MB。
2. 其中混入了大量**不可达条目**——正文键在对应 `meta.json` 里根本找不到对应文章，
   前端 `meta.findIndex(a => a.u === url)` 永远匹配不到，属于纯粹的死重。
   实测：`data/years/2026.json` 1641 条里有 1342 条不可达
   （1120 条是 qstheory.cn 域的求是文章，222 条是 http/https 协议变体重复）。

本脚本做四件事（全部可 `--dry-run` 预演）：

1. 按（年, 期）把正文重新分片写入 `data/<mag>/issues/<year>-<issue>.json`；
2. 丢弃不可达条目；协议变体（http vs https）能对应上 meta 的自动归并；
3. 重建 `data/article_index.json`，只保留 meta.json 里能寻址到的条目；
4. 生成 `data/counts.json`（首页计数，避免为了三个数字下载 1.3 MB 的 meta.json）。

用法
----
```bash
python scripts/rebuild_data.py            # 预演，只报告
python scripts/rebuild_data.py --apply    # 实际写盘
```
"""
import json
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAGAZINES = {
    'qs': {
        'name': '求是',
        'meta': 'data/qs/meta.json',
        'years': 'data/qs/years',
        'issues': 'data/qs/issues',
    },
    'hqwg': {
        'name': '红旗文稿',
        'meta': 'data/hqwg/meta.json',
        'years': 'data/hqwg/years',
        'issues': 'data/hqwg/issues',
    },
    'djyj': {
        'name': '党建研究',
        'meta': 'data/meta.json',
        'years': 'data/years',
        'issues': 'data/issues',
    },
}


def log(s=''):
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode('utf-8', 'replace').decode('utf-8', 'replace'))


def load_json(rel):
    path = os.path.join(BASE_DIR, rel)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def dump_json(rel, obj):
    path = os.path.join(BASE_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def file_size(rel):
    path = os.path.join(BASE_DIR, rel)
    return os.path.getsize(path) if os.path.exists(path) else 0


def https_variant(url):
    """http://x/a 与 https://x/a 视为同一篇文章。"""
    if url.startswith('http://'):
        return 'https://' + url[7:]
    if url.startswith('https://'):
        return 'http://' + url[8:]
    return None


def rebuild_magazine(key, conf, apply):
    meta = load_json(conf['meta']) or []
    meta_by_url = {}
    url_to_issue = {}
    for a in meta:
        meta_by_url[a['u']] = a
        url_to_issue[a['u']] = (a['y'], a['i'])

    # 合并所有年份正文
    years_dir = os.path.join(BASE_DIR, conf['years'])
    body = {}
    dup_conflict = 0
    if os.path.isdir(years_dir):
        for fn in sorted(os.listdir(years_dir)):
            if not fn.endswith('.json'):
                continue
            data = load_json(os.path.join(conf['years'], fn)) or {}
            for u, text in data.items():
                if u in body and body[u] != text:
                    dup_conflict += 1
                body[u] = text

    # 分片：正文 → (年, 期)
    shards = {}
    orphan = 0
    orphan_sample = []
    merged_variant = 0
    for u, text in body.items():
        target = url_to_issue.get(u)
        key_url = u
        if target is None:
            # 协议变体归并：正文是 http://，meta 里记的是 https://（或反之）。
            # 归并后**用 meta 里的规范 URL 作键**，避免同一篇文章在分片里出现两份正文。
            alt = https_variant(u)
            if alt and alt in url_to_issue:
                target = url_to_issue[alt]
                key_url = alt
                merged_variant += 1
            else:
                orphan += 1
                if len(orphan_sample) < 5:
                    orphan_sample.append(u)
                continue
        items = shards.setdefault(target, {})
        if key_url in items:
            continue          # 同一篇文章的另一个变体已在分片里，保留先到的那份
        items[key_url] = text

    # 体检：meta 标了有正文、但正文数据里找不到的
    missing = [a for a in meta if a['h'] == 1 and a['u'] not in body]
    # 体检：哪些期次一个分片都没有（该期正文整体缺失）
    meta_issues = set('%s-%s' % (a['y'], a['i']) for a in meta)
    shard_issues = set('%s-%s' % (y, i) for (y, i) in shards)
    no_body_issues = sorted(meta_issues - shard_issues)

    old_total = sum(file_size(os.path.join(conf['years'], fn))
                    for fn in os.listdir(years_dir)) if os.path.isdir(years_dir) else 0
    new_total = 0

    if apply:
        issues_dir = os.path.join(BASE_DIR, conf['issues'])
        if os.path.isdir(issues_dir):
            shutil.rmtree(issues_dir)
        os.makedirs(issues_dir, exist_ok=True)
        for (year, issue), items in sorted(shards.items()):
            rel = os.path.join(conf['issues'], '%d-%d.json' % (year, issue))
            dump_json(rel, items)
            new_total += file_size(rel)

    log('  [%s] meta=%d  正文键=%d' % (key, len(meta), len(body)))
    log('       分片数=%d  可达正文=%d  丢弃不可达=%d（其中协议变体归并=%d）'
        % (len(shards), sum(len(v) for v in shards.values()), orphan, merged_variant))
    if orphan_sample:
        log('       不可达样例：')
        for u in orphan_sample:
            log('         - ' + u)
    if missing:
        log('       ⚠ meta 标记有正文但正文数据缺失：%d 条（历史遗留，非本次重建引入）'
            % len(missing))
        for a in missing[:5]:
            log('         - %s | %s' % (a['t'][:28], a['u']))
    if no_body_issues:
        log('       ⚠ 整期无正文的期次 %d 个：%s'
            % (len(no_body_issues), ', '.join(no_body_issues[:8])))
    if dup_conflict:
        log('       （同 URL 在多个年份文件里正文不一致：%d 处，取后者）' % dup_conflict)
    if apply:
        log('       正文体积：%.2f MB → %.2f MB（省 %.0f%%）'
            % (old_total / 1048576, new_total / 1048576,
               (1 - new_total / old_total) * 100 if old_total else 0))
    return {
        'articles': len(meta),
        'issues': len(meta_issues),
    }, missing, orphan


def rebuild_article_index(apply):
    """只保留 meta.json 里能寻址到的条目。"""
    idx = load_json('data/article_index.json') or {}
    before = sum(len(v) for v in idx.values())
    before_size = file_size('data/article_index.json')
    new_idx = {}
    dropped = 0
    for key, conf in MAGAZINES.items():
        meta = load_json(conf['meta']) or []
        valid = set(a['u'] for a in meta)
        src = idx.get(key, {})
        kept = {u: p for u, p in src.items() if u in valid}
        dropped += len(src) - len(kept)
        new_idx[key] = kept
    after = sum(len(v) for v in new_idx.values())
    if apply:
        dump_json('data/article_index.json', new_idx)
    log('  [article_index] 条目 %d → %d（丢弃 %d 条不可达）'
        % (before, after, dropped))
    if apply:
        log('       体积 %.2f MB → %.2f MB'
            % (before_size / 1048576, file_size('data/article_index.json') / 1048576))
    return before, after


def write_counts(counts, apply):
    if apply:
        dump_json('data/counts.json', counts)
    log('  [counts] %s' % json.dumps(counts, ensure_ascii=False, separators=(',', ':')))


def main():
    apply = '--apply' in sys.argv
    log('=' * 72)
    log('正文数据重建（按期分片 + 去污染 + 索引瘦身）')
    log('模式：%s' % ('实际写盘' if apply else '预演（加 --apply 才会写）'))
    log('=' * 72)

    counts = {}
    all_missing = 0
    all_orphan = 0
    for key, conf in MAGAZINES.items():
        c, missing, orphan = rebuild_magazine(key, conf, apply)
        counts[key] = c
        all_missing += len(missing)
        all_orphan += orphan
        log('')

    rebuild_article_index(apply)
    write_counts(counts, apply)

    log('')
    if all_missing:
        log('⚠ 共 %d 条 meta 标记有正文但正文数据缺失（历史遗留，重建不阻塞）' % all_missing)
    if all_orphan:
        log('（已丢弃 %d 条不可达正文，它们在 meta.json 里没有对应文章）' % all_orphan)
    log('✅ 重建完成')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
