"""Build year-sized, on-demand full-text search files for the speech library."""
from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/speeches/index.json"
OUTPUT = ROOT / "data/speeches/body_search"


def plain_text(markdown):
    markdown = re.sub(r"!\[[^]]*\]\([^)]*\)", " ", markdown)
    markdown = re.sub(r"<[^>]*>", " ", markdown)
    markdown = re.sub(r"\*\*|^#{1,6}\s*", "", markdown, flags=re.M)
    return re.sub(r"\s+", " ", markdown).strip()


def build():
    items = json.loads(SOURCE.read_text("utf-8"))["items"]
    years = {}
    for item in items:
        if not item["p"]:
            continue
        article_id = re.search(r"ARTI\d+", item["p"]).group()
        body = plain_text((ROOT / item["p"]).read_text("utf-8"))
        years.setdefault(str(item["y"]), []).append([article_id, body])
    return {year: json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for year, rows in years.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for year, data in files.items():
        path = OUTPUT / (year + ".json")
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                raise SystemExit(f"Stale speech body search file: {path}")
        else:
            path.write_bytes(data)
    print(f"Speech body search: {len(files)} years, {sum(map(len, files.values()))} bytes")


if __name__ == "__main__":
    main()
