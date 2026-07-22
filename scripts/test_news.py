"""
Manual test harness for the news signal (Phase 1 — monitor-only validation).

Runs live.news_signal.assess_news() against one or more symbols WITHOUT touching
the live trading loop, so you can eyeball relevance, sentiment quality, source,
and latency before wiring it in.

Usage (from repo root, venv active):
    python -m scripts.test_news RELIANCE LONG
    python -m scripts.test_news INDUSINDBK SHORT
    python -m scripts.test_news RELIANCE:LONG TCS:SHORT HDFCBANK:LONG
    python -m scripts.test_news --headlines-only RELIANCE     # fetch + print raw headlines only

Requires GEMINI_API_KEY in .env when NEWS_CLASSIFIER="gemini" (otherwise it
falls back to the offline keyword classifier and reports source=keyword).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date

# Headlines can contain ₹ and other non-cp1252 glyphs; force UTF-8 console output
# so printing them doesn't blow up on Windows (default console is cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from live import news_signal as ns  # noqa: E402


def _parse_targets(tokens: list[str], default_dir: str) -> list[tuple[str, str]]:
    """Accept 'SYMBOL DIR' pairs, 'SYMBOL:DIR' tokens, or bare symbols."""
    targets: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if ":" in tok:
            sym, _, d = tok.partition(":")
            targets.append((sym.upper(), _norm(d) or default_dir))
            i += 1
        elif i + 1 < len(tokens) and _norm(tokens[i + 1]):
            targets.append((tok.upper(), _norm(tokens[i + 1])))
            i += 2
        else:
            targets.append((tok.upper(), default_dir))
            i += 1
    return targets


def _norm(d: str) -> str:
    d = (d or "").upper()
    if d.startswith("L"):
        return "LONG"
    if d.startswith("S"):
        return "SHORT"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Test the news signal for given symbols.")
    ap.add_argument("targets", nargs="+",
                    help="SYMBOL [LONG|SHORT] pairs, or SYMBOL:DIR tokens, or bare symbols")
    ap.add_argument("--dir", default="LONG", help="default direction when unspecified")
    ap.add_argument("--headlines-only", action="store_true",
                    help="only fetch and print raw headlines (no classifier call)")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore any cached result for today")
    args = ap.parse_args()

    targets = _parse_targets(args.targets, _norm(args.dir) or "LONG")
    today = date.today()

    for symbol, direction in targets:
        company = ns.company_name_for(symbol)
        print("\n" + "=" * 72)
        print(f"{symbol}  [{direction}]   company='{company}'")
        print("-" * 72)

        if args.headlines_only:
            query = ns._build_query(company, symbol)
            print(f"query: {query}")
            t0 = time.time()
            try:
                items = ns._fetch_headlines(query)
            except Exception as e:  # noqa: BLE001
                print(f"  fetch failed: {e}")
                continue
            print(f"  {len(items)} items in last {ns.NEWS_LOOKBACK_HOURS}h "
                  f"({(time.time() - t0):.2f}s):")
            for it in items:
                print(f"   [{it['pubdate']:%Y-%m-%d %H:%M}Z] {it['source']}: {it['title']}")
            continue

        if args.no_cache:
            path = ns._cache_path(today, symbol)
            if path.exists():
                path.unlink()

        t0 = time.time()
        result = ns.assess_news(symbol, company, direction, today)
        dt = time.time() - t0

        print(f"  news_signal   : {result['news_signal']}")
        print(f"  news_score    : {result['news_score']:+.2f}   (aligned to {direction})")
        print(f"  news_conf     : {result['news_conf']:.2f}")
        print(f"  news_count    : {result['news_count']}")
        print(f"  news_source   : {result['news_source']}")
        print(f"  news_headline : {result['news_headline']}")
        print(f"  latency       : {dt:.2f}s")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
