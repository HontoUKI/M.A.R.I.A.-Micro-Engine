"""DuckDuckGo Lite parsing (pure, no network)."""
from __future__ import annotations

from engine.web import DuckDuckGoSearcher, parse_results

_FIXTURE = """
<html><body><table>
<tr><td>
  <a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpython">
    Python (programming language)
  </a>
</td></tr>
<tr><td class="result-snippet">Python is a high-level programming language.</td></tr>
<tr><td>
  <a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org">
    Python docs
  </a>
</td></tr>
<tr><td class="result-snippet">Official documentation for Python.</td></tr>
</table></body></html>
"""


def test_parse_extracts_title_url_and_snippet():
    results = parse_results(_FIXTURE)
    assert len(results) == 2
    first = results[0]
    assert first.title == "Python (programming language)"
    assert first.url == "https://example.com/python"  # uddg redirect unwrapped
    assert "high-level" in first.snippet


def test_parse_respects_limit():
    assert len(parse_results(_FIXTURE, limit=1)) == 1


def test_parse_returns_empty_on_bot_challenge_page():
    assert parse_results("<html>challenge-form here</html>") == []


def test_parse_empty_html_yields_nothing():
    assert parse_results("<html></html>") == []


def test_searcher_returns_empty_for_blank_query_without_network():
    # A blank query short-circuits before any network call.
    assert DuckDuckGoSearcher().search("   ") == []
