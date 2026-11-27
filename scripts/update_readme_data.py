"""Keep README's data-range table in sync with the published archive."""

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MAGAZINES = (
    ("qs", "求是", "data/qs/meta.json"),
    ("hqwg", "红旗文稿", "data/hqwg/meta.json"),
    ("djyj", "党建研究", "data/meta.json"),
    ("qz", "旗帜", "data/qz/meta.json"),
)
SECTION = re.compile(r"(?<=## 数据范围\n\n)[\s\S]*?(?=\n## 项目结构)")


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def build_section():
    homepage = (ROOT / "index.html").read_text(encoding="utf-8")
    match = re.search(r"最近一次数据采集更新时间：<strong>([^<]+)", homepage)
    if not match:
        raise RuntimeError("Homepage data update date not found")
    counts = read_json("data/counts.json")
    lines = [
        f"以下是截至 {match.group(1)}的仓库数据快照；最新数据请查看网站首页和 `data/counts.json`。",
        "",
        "| 来源 | 覆盖范围 | 文章 | 期数 |",
        "| --- | --- | ---: | ---: |",
    ]
    for key, name, path in MAGAZINES:
        items = read_json(path)
        if not items:
            raise RuntimeError(f"Empty magazine catalog: {key}")
        first = min((item["y"], item["i"]) for item in items)
        latest = max((item["y"], item["i"]) for item in items)
        actual_issues = len({(item["y"], item["i"]) for item in items})
        recorded = counts[key]
        if recorded["articles"] != len(items) or recorded["issues"] != actual_issues:
            raise RuntimeError(f"Counts and catalog disagree: {key}")
        lines.append(
            f"| 《{name}》 | {first[0]} 年第 {first[1]} 期至 {latest[0]} 年第 {latest[1]} 期 "
            f"| {len(items):,} | {actual_issues} |"
        )
    speeches = read_json("data/speeches/index.json")["items"]
    if not speeches:
        raise RuntimeError("Empty speech catalog")
    readable = sum(bool(item.get("p")) for item in speeches)
    years = [item["y"] for item in speeches]
    lines.extend([
        f"| 习近平讲话库 | {min(years)}—{max(years)} 年 | {len(speeches):,} | 按年浏览 |",
        "",
        f"讲话库有 {readable:,} 篇已归档正文、{len(speeches) - readable:,} 篇官网原文暂不可读取。"
        "部分刊物旧文章也缺少可读取的全文；目录仍保留这些条目，并提供官网来源信息。",
        "",
    ])
    return "\n".join(lines)


def update(check=False):
    path = ROOT / "README.md"
    old_raw = path.read_bytes().decode("utf-8")
    line_ending = "\r\n" if "\r\n" in old_raw else "\n"
    old = old_raw.replace("\r\n", "\n")
    new, count = SECTION.subn(lambda _: build_section(), old)
    if count != 1:
        raise RuntimeError("README data range section not found exactly once")
    new_raw = new.replace("\n", line_ending)
    if check:
        if new_raw != old_raw:
            raise RuntimeError("README data range is stale; run python scripts/update_readme_data.py")
        print("README data range matches the archive")
    elif new_raw != old_raw:
        path.write_bytes(new_raw.encode("utf-8"))
        print("Updated README data range")
    return new_raw != old_raw


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if README data range is stale")
    args = parser.parse_args()
    update(check=args.check)
