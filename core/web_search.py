"""
Shared web-search helpers.
"""

from __future__ import annotations

import os
import warnings
from urllib.parse import urlparse

import requests

from core.env import load_app_env
from core.time_window import search_time_filter
try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - optional dependency
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

# Load env-backed search credentials before helper functions run.
load_app_env()


# Read the optional Serper key from the shared environment.
def _serper_api_key() -> str:
    return (os.getenv("SERPER_API_KEY") or "").strip()


# Query Serper across as many pages as needed while de-duplicating result links.
def serper_text_search(query: str) -> list[dict]:
    api_key = _serper_api_key()
    if not api_key:
        return []

    serper_filter, _ = search_time_filter()
    results: list[dict] = []
    seen_links: set[str] = set()
    page = 1
    while True:
        payload = {
            "q": query,
            "page": page,
        }
        if serper_filter is not None:
            payload["tbs"] = serper_filter
        with requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        ) as response:
            response.raise_for_status()
            response_payload = response.json()
        organic_items = response_payload.get("organic") or []
        if not organic_items:
            break

        new_links = 0
        for item in organic_items:
            link = str(item.get("link") or "")
            if not link or link in seen_links:
                continue
            results.append(
                {
                    "title": item.get("title") or "",
                    "href": link,
                    "body": item.get("snippet") or "",
                }
            )
            seen_links.add(link)
            new_links += 1

        if new_links == 0:
            break
        page += 1

    return results


# Query DuckDuckGo with the shared lookback filter and graceful fallbacks.
def duckduckgo_text_search(query: str) -> list[dict]:
    if DDGS is None:
        return []
    _, ddg_filter = search_time_filter()
    search_args = {"max_results": None}
    fallback_args = {}
    if ddg_filter is not None:
        search_args["timelimit"] = ddg_filter
        fallback_args["timelimit"] = ddg_filter

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*duckduckgo_search.*renamed to `ddgs`.*", category=RuntimeWarning)
            with DDGS() as ddgs:
                return list(ddgs.text(query, **search_args))
    except Exception:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=r".*duckduckgo_search.*renamed to `ddgs`.*", category=RuntimeWarning)
                with DDGS() as ddgs:
                    return list(ddgs.text(query, **fallback_args))
        except Exception:
            return []


# Merge Serper and DuckDuckGo results while preserving unique links.
def combined_text_search(queries: list[str]) -> list[dict]:
    merged: list[dict] = []
    seen_links: set[str] = set()

    for query in queries:
        for search_fn in (serper_text_search, duckduckgo_text_search):
            try:
                results = search_fn(query)
            except Exception:
                continue
            for item in results:
                link = str(item.get("href") or "")
                if not link or link in seen_links:
                    continue
                merged.append(item)
                seen_links.add(link)

    return merged


# Break a URL path into parts for downstream platform-specific parsing.
def path_parts(url: str) -> list[str]:
    return [part for part in urlparse(url).path.split("/") if part]
