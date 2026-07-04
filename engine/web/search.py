"""DuckDuckGo Lite search (stdlib only), ported from the Lisa prototype.

The HTML parsing is pure and unit-tested against a fixture; the network fetch is
isolated so tests never touch the internet. Search only ever hits the fixed
DuckDuckGo Lite endpoint — there is no arbitrary-URL fetching, so no SSRF risk.
Any failure returns an empty list; a web lookup must never crash a turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from engine.logging_config import get_logger

_log = get_logger("web")

_ENDPOINT = "https://lite.duckduckgo.com/lite/?q="
_USER_AGENT = "Mozilla/5.0 (compatible; MicroEngine/0.1; +https://github.com/HontoUKI)"


@dataclass(frozen=True)
class WebResult:
    """One search hit: enough to ground a reply without fetching the page."""

    title: str
    url: str
    snippet: str


class WebSearcher(Protocol):
    """Anything that can turn a query into result snippets (injectable)."""

    def search(self, query: str) -> list[WebResult]:
        ...


class _DuckDuckGoParser(HTMLParser):
    """Extracts (title, url, snippet) triples from a DuckDuckGo Lite page."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[WebResult] = []
        self._in_title = False
        self._in_snippet = False
        self._url = ""
        self._title: list[str] = []
        self._snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = attr_map.get("class", "")
        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self._in_title = True
            self._url = _clean_url(attr_map.get("href", ""))
            self._title = []
            self._snippet = []
        elif "result__snippet" in classes or "result-snippet" in classes:
            self._in_snippet = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)
        elif self._in_snippet:
            self._snippet.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        elif self._in_snippet and tag in {"a", "div", "td"}:
            self._in_snippet = False
            self._flush()

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        title = " ".join(" ".join(self._title).split())
        snippet = " ".join(" ".join(self._snippet).split())
        if title and self._url and not any(r.url == self._url for r in self.results):
            self.results.append(WebResult(title=title, url=self._url, snippet=snippet))
        self._title = []
        self._snippet = []
        self._url = ""


def _clean_url(url: str) -> str:
    if url.startswith("//"):
        url = f"https:{url}"
    redirect = parse_qs(urlparse(url).query).get("uddg")
    return unquote(redirect[0]) if redirect else url


def parse_results(html: str, *, limit: int = 3) -> list[WebResult]:
    """Parse a DuckDuckGo Lite results page (pure; used by tests)."""
    if "challenge-form" in html or "anomaly.js" in html:
        return []
    parser = _DuckDuckGoParser()
    parser.feed(html)
    parser.close()
    return parser.results[:limit]


class DuckDuckGoSearcher:
    """Live searcher hitting DuckDuckGo Lite. Never raises — returns []."""

    def __init__(self, *, limit: int = 3, timeout_s: float = 8.0) -> None:
        self._limit = limit
        self._timeout_s = timeout_s

    def search(self, query: str) -> list[WebResult]:
        query = (query or "").strip()
        if not query:
            return []
        request = Request(_ENDPOINT + quote_plus(query), headers={"User-Agent": _USER_AGENT})
        try:
            with urlopen(request, timeout=self._timeout_s) as response:  # noqa: S310 (fixed host)
                html = response.read().decode("utf-8", errors="replace")
        except (URLError, TimeoutError, ValueError) as exc:
            _log.warning("web search failed: %s", exc)
            return []
        return parse_results(html, limit=self._limit)
