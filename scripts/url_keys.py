"""Stable comparison keys for official magazine article URLs."""
import re


def url_key(url):
    url = re.sub(r"(/dukan/(?:qs|hqwg)/)\d{4}/", r"\1", url or "")
    return re.sub(r"^https?://", "", url).lower()
