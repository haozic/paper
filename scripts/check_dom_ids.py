"""Ensure the main page and lazy speech shell do not define duplicate IDs."""

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        self.ids.extend(value for name, value in attrs if name == "id" and value)


collector = IdCollector()
collector.feed((ROOT / "index.html").read_text("utf-8"))
collector.feed((ROOT / "speeches/shell.txt").read_text("utf-8"))
duplicates = [name for name, count in Counter(collector.ids).items() if count > 1]
if duplicates:
    raise SystemExit(f"Duplicate DOM IDs after speech shell loads: {duplicates}")
print(f"DOM IDs unique across main page and speech shell: {len(collector.ids)}")
