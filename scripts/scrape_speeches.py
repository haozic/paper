"""Archive the official 12371 important speeches catalog for the static library."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from scrape_magazines import element_to_md

ROOT = Path(__file__).resolve().parents[1]
CATALOG = "https://www.12371.cn/special/xxzd/jh/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PaperArchive/1.0)"}


def fetch(url):
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=25)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def catalog():
    soup = BeautifulSoup(fetch(CATALOG), "html.parser")
    entries = []
    seen = set()
    for link in soup.select('a[href*="ARTI"]'):
        url = link.get("href", "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in {
            "www.12371.cn", "news.12371.cn", "syss.12371.cn", "biaozhang.12371.cn"
        }:
            continue
        match = re.search(r"/(20\d\d)/\d\d/\d\d/(ARTI\d+)\.shtml$", parsed.path)
        if not match or url in seen:
            continue
        seen.add(url)
        item = link.find_parent("li")
        summary = item.select_one(".cont") if item else None
        entries.append({
            "t": link.get_text(" ", strip=True),
            "u": url,
            "y": int(match.group(1)),
            "d": summary.get_text(" ", strip=True) if summary else "",
            "p": f"articles/speeches/{match.group(1)}/{match.group(2)}.md",
        })
    if len(entries) < 1000:
        raise RuntimeError(f"Catalog unexpectedly short: {len(entries)}")
    return entries


def article(entry):
    path = ROOT / entry["p"]
    if "--refresh" not in sys.argv and path.exists() and len(path.read_text("utf-8")) > 100:
        return entry, None
    soup = BeautifulSoup(fetch(entry["u"]), "html.parser")
    word = soup.select_one("#font_area .word")
    if not word:
        raise ValueError(f"Missing article body: {entry['u']}")
    for unwanted in word.select("script, style, noscript"):
        unwanted.decompose()
    body = element_to_md(word, entry["u"]).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = "\n".join(line.rstrip() for line in body.splitlines())
    if len(body) < 100 or "�" in body:
        raise ValueError(f"Invalid article body: {entry['u']} ({len(body)} chars)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((body + "\n").encode("utf-8"))
    return entry, path


def main():
    entries = catalog()
    print(f"Official catalog: {len(entries)} unique articles", flush=True)
    failures = []
    unavailable = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(article, entry): entry for entry in entries}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                future.result()
            except ValueError as exc:
                if str(exc).startswith("Missing article body:"):
                    futures[future]["p"] = None
                    unavailable.append(futures[future]["u"])
                else:
                    failures.append((futures[future]["u"], str(exc)))
            except Exception as exc:
                failures.append((futures[future]["u"], str(exc)))
            if done % 100 == 0 or done == len(entries):
                print(f"{done}/{len(entries)} processed; {len(failures)} failures", flush=True)
    if failures:
        print("Failed articles:", *failures[:30], sep="\n", file=sys.stderr)
        return 1
    if unavailable:
        print(f"Official pages without retrievable text: {len(unavailable)}", *unavailable, sep="\n", flush=True)
    output = ROOT / "data/speeches/index.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps({"source": CATALOG, "items": entries}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print(f"Wrote {output.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
