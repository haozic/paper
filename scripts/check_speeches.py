"""Validate the independently archived 12371 speeches library."""
from pathlib import Path
from urllib.parse import urlparse
import json
import re

root = Path(__file__).resolve().parents[1]
items = json.loads((root / "data/speeches/index.json").read_text("utf-8"))["items"]
assert len(items) >= 1500, len(items)
assert len({item["u"] for item in items}) == len(items)
assert all(item["t"] and item["d"] for item in items)
assert all(urlparse(item["u"]).hostname in {"www.12371.cn", "news.12371.cn", "syss.12371.cn", "biaozhang.12371.cn"} for item in items)
assert all(re.search(r"/ARTI\d+\.md$", item["p"]) and len((root / item["p"]).read_text("utf-8")) >= 100 for item in items if item["p"])
missing = [item for item in items if not item["p"]]
assert len(missing) == 5, len(missing)
print(f"讲话库：{len(items)} 条目录、{len(items)-len(missing)} 篇正文、{len(missing)} 篇官网失效")
