"""Check official catalogs and update the static archive when new content exists.

Run with --check-only to inspect sources without writing files. The scheduled
GitHub workflow runs this script before validation and publication.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import scrape_magazines as magazines
import scrape_qizhi as qizhi
import scrape_speeches as speeches


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve().parent
MAGAZINES = ("qs", "hqwg", "djyj")
ISSUES_PER_YEAR = {"qs": 24, "hqwg": 24, "djyj": 12}
VERSION_FILES = ("index.html", "assets/js/app.js", "sw.js", "speeches/shell.txt", "speeches/speeches.js")


def run(script, *args):
    subprocess.run([sys.executable, str(SCRIPT / script), *map(str, args)], cwd=ROOT, check=True)


def missing_issues(local, latest, per_year):
    if latest <= local:
        return []
    pending = []
    for year in range(local[0], latest[0] + 1):
        first = local[1] + 1 if year == local[0] else 1
        last = latest[1] if year == latest[0] else per_year
        pending.extend((year, issue) for issue in range(first, last + 1))
    if len(pending) > 6:
        raise RuntimeError(f"Too many missing issues ({len(pending)}): inspect catalogs manually")
    return pending


def read_items(path):
    return json.loads((ROOT / path).read_text("utf-8"))


def issue_set(magazine):
    path = magazines.MAGAZINES[magazine]["meta_path"]
    return {(item["y"], item["i"]) for item in read_items(path)}


def new_version():
    old = re.search(r"^const VERSION = '([^']+)';", (ROOT / "speeches/speeches.js").read_text("utf-8"), re.M).group(1)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if re.fullmatch(r"\d{14}", old) and version <= old:
        version = (datetime.strptime(old, "%Y%m%d%H%M%S") + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")
    for name in VERSION_FILES:
        path = ROOT / name
        text = path.read_text("utf-8")
        if old not in text:
            raise RuntimeError(f"Missing current version in {name}")
        if name == "assets/js/app.js":
            text = re.sub(r"(const DATA_VERSION = .* \|\| ')[^']+(';)", rf"\g<1>{version}\g<2>", text, count=1)
        path.write_text(text.replace(old, version), encoding="utf-8")
    index = ROOT / "scripts/build_search_index.py"
    text = index.read_text("utf-8")
    text, count = re.subn(r"^INDEX_VERSION = '[^']+'$", f"INDEX_VERSION = '{version}'", text, count=1, flags=re.M)
    if count != 1:
        raise RuntimeError("Search index version not found")
    index.write_text(text, encoding="utf-8")
    return version


def update_about():
    path = ROOT / "index.html"
    html = path.read_text("utf-8")
    today = datetime.now(timezone(timedelta(hours=8)))
    date = f"{today.year} 年 {today.month} 月 {today.day} 日"
    html, count = re.subn(r"(最近一次数据采集更新时间：<strong>)[^<]+", rf"\g<1>{date}", html, count=1)
    if count != 1:
        raise RuntimeError("About-page update date not found")
    for key, name in (("qs", "求是"), ("hqwg", "红旗文稿"), ("djyj", "党建研究"), ("qz", "旗帜")):
        year, issue = max(issue_set(key))
        pattern = rf"(《{name}》：\d{{4}} 年第 \d+ 期 至 )\d{{4}} 年第 \d+ 期"
        html, count = re.subn(pattern, rf"\g<1>{year} 年第 {issue} 期", html, count=1)
        if count != 1:
            raise RuntimeError(f"About-page range not found: {name}")
    items = read_items("data/speeches/index.json")["items"]
    readable = sum(bool(item["p"]) for item in items)
    years = [item["y"] for item in items]
    html, count = re.subn(r"习近平讲话库：\d{4} 年至 \d{4} 年，\d+ 条目录记录；\d+ 篇可阅读正文",
                           f"习近平讲话库：{min(years)} 年至 {max(years)} 年，{len(items)} 条目录记录；{readable} 篇可阅读正文", html, count=1)
    if count != 1:
        raise RuntimeError("About-page speech count not found")
    html, count = re.subn(r'(<h2>习近平讲话库</h2>[\s\S]*?<p class="mag-meta">)\d+ 篇 · \d{4}—\d{4}',
                           rf'\g<1>{len(items)} 篇 · {min(years)}—{max(years)}', html, count=1)
    if count != 1:
        raise RuntimeError("Home-page speech count not found")
    path.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="Read official catalogs without changing files")
    args = parser.parse_args()

    pending = {}
    for key in MAGAZINES:
        local = magazines.get_local_latest_issue(key)
        latest = magazines.get_latest_issue(key)
        if not local or not latest:
            raise RuntimeError(f"Cannot determine latest issue: {key}")
        pending[key] = missing_issues(local, latest, ISSUES_PER_YEAR[key])
        print(f"{magazines.MAGAZINES[key]['name']}: local {local}, official {latest}, pending {pending[key]}", flush=True)

    local_qz = issue_set("qz")
    remote_qz = qizhi.archive_issues()
    pending["qz"] = [row[:2] for row in remote_qz if row[:2] not in local_qz]
    if len(pending["qz"]) > 6:
        raise RuntimeError("Too many missing Qizhi issues: inspect official archive manually")
    print(f"旗帜: local {max(local_qz)}, official {remote_qz[0][:2]}, pending {pending['qz']}", flush=True)

    local_speeches = read_items("data/speeches/index.json")["items"]
    remote_speeches = speeches.catalog()
    known = {item["u"] for item in local_speeches}
    new_speeches = [item for item in remote_speeches if item["u"] not in known]
    if len(remote_speeches) < len(local_speeches) or len(new_speeches) > 30:
        raise RuntimeError("Unexpected speech catalog change: inspect official source manually")
    print(f"讲话库: local {len(local_speeches)}, official {len(remote_speeches)}, new {len(new_speeches)}", flush=True)

    if args.check_only or not any(pending.values()) and not new_speeches:
        print("Check complete; no files changed", flush=True)
        return 0

    for key in MAGAZINES:
        for year, issue in pending[key]:
            run("scrape_magazines.py", key, year, issue)
            if (year, issue) not in issue_set(key):
                raise RuntimeError(f"Missing archived issue after scrape: {key} {year}-{issue}")
    if pending["qz"]:
        run("scrape_qizhi.py")
        if not set(pending["qz"]).issubset(issue_set("qz")):
            raise RuntimeError("Missing Qizhi issue after scrape")
    if new_speeches:
        run("scrape_speeches.py")
        archived = {item["u"] for item in read_items("data/speeches/index.json")["items"]}
        if not {item["u"] for item in new_speeches}.issubset(archived):
            raise RuntimeError("Missing speech after scrape")
        run("build_speech_body_search.py")

    magazines.write_counts()
    version = new_version()
    update_about()
    run("build_search_index.py")
    print(f"Archive updated; resource version {version}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
