#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build the tiny homepage latest-article payload from magazine metadata."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = [('qs', 'data/qs/meta.json'), ('hqwg', 'data/hqwg/meta.json'), ('djyj', 'data/meta.json')]

def main():
    latest = {}
    for mag, rel in SOURCES:
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            meta = json.load(f)
        entries = sorted(meta, key=lambda a: (-a['y'], -a['i']))
        article = next((a for a in entries if a.get('t') != '本期导读'), None)
        if article:
            latest[mag] = {k: article[k] for k in ('y', 'i', 't', 'u')}
    out = os.path.join(ROOT, 'data', 'latest.json')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(latest, f, ensure_ascii=False, separators=(',', ':'))
    print('Generated data/latest.json (%d bytes)' % os.path.getsize(out))

if __name__ == '__main__':
    main()
