"""Research a topic with the Tavily search API and save the results as JSON.

Usage:
    .venv/bin/python tools/research_topic.py "AI regulation in the EU" \
        --query "EU AI Act enforcement timeline 2026" \
        --query "EU AI Act impact on enterprises statistics"

The topic itself is always searched. Each extra --query is searched too.
Output: .tmp/research/<slug>.json with an answer and sources for every query.
Cost: "advanced" depth uses 2 Tavily credits per query, "basic" uses 1.
"""
import argparse
import json
import os
from datetime import datetime, timezone

from _common import TMP, fail, slugify

import requests

TAVILY_URL = "https://api.tavily.com/search"


def search(api_key, query, depth, max_results, topic, time_range):
    body = {
        "query": query,
        "search_depth": depth,
        "max_results": max_results,
        "include_answer": "advanced",
        "topic": topic,
    }
    if time_range:
        body["time_range"] = time_range
    resp = requests.post(
        TAVILY_URL,
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if resp.status_code == 401:
        fail("Tavily rejected the API key. Check TAVILY_API_KEY in .env.")
    if resp.status_code == 429:
        fail("Tavily rate limit or monthly credit limit reached (HTTP 429).")
    if not resp.ok:
        fail(f"Tavily returned HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return {
        "query": query,
        "answer": data.get("answer"),
        "sources": [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
                "published_date": r.get("published_date"),
                "score": r.get("score"),
            }
            for r in data.get("results", [])
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("topic", help="The newsletter topic")
    p.add_argument("--query", action="append", default=[], help="Extra search query (repeatable)")
    p.add_argument("--depth", choices=["basic", "advanced"], default="advanced")
    p.add_argument("--max-results", type=int, default=6)
    p.add_argument("--news", action="store_true", help="Search news sources instead of the general web")
    p.add_argument("--time-range", choices=["day", "week", "month", "year"], help="Limit results to a recent window")
    args = p.parse_args()

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        fail("TAVILY_API_KEY is empty. Paste your key into .env.")

    queries = [args.topic] + [q for q in args.query if q.strip()]
    topic = "news" if args.news else "general"
    results = []
    for q in queries:
        print(f"Searching: {q}")
        results.append(search(api_key, q, args.depth, args.max_results, topic, args.time_range))

    out_dir = TMP / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slugify(args.topic)}.json"
    out_path.write_text(json.dumps({
        "topic": args.topic,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": results,
    }, indent=2, ensure_ascii=False))

    n_sources = sum(len(r["sources"]) for r in results)
    print(f"Saved {len(results)} queries, {n_sources} sources -> {out_path.relative_to(TMP.parent)}")


if __name__ == "__main__":
    main()
