"""Optional, opt-in web lookup.

A deliberately small capability: when a pack declares a `web_lookup` tag and
`WEB_SEARCH` is enabled, a turn classified as needing outside information runs a
lightweight DuckDuckGo search and the result snippets are handed to the voicing
model as grounding. Off by default — the community tier ships no network access
unless a deployer turns it on.

Ported from the public "little-agent-planner" (Lisa) prototype
(github.com/HontoUKI/Sandbox_with_LLM): stdlib only, no API key, snippets only
(no arbitrary page fetching, so no SSRF surface).
"""

from engine.web.search import DuckDuckGoSearcher, WebResult, WebSearcher, parse_results

__all__ = ["DuckDuckGoSearcher", "WebResult", "WebSearcher", "parse_results"]
