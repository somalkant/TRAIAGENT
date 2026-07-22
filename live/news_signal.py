"""
News signal — MONITOR ONLY (Phase 2.7).

At entry time we pull yesterday's/today's headlines for the traded symbol from
Google News RSS, ask a classifier (Gemini Flash by default) whether the news is
bullish or bearish for the stock, then align that judgement to OUR trade
direction (LONG/SHORT). The result is written to the trade log (news_* columns)
and one NEWS line to the run log.

Design guarantees:
  * assess_news() NEVER raises and NEVER blocks a trade. Any failure/timeout
    returns a well-formed dict with news_signal="UNAVAILABLE" and the caller
    proceeds exactly as if news didn't exist.
  * It runs at most once per placed trade (1-2x/day), off the scan path.
  * Results are cached per (trade_date, symbol) so re-scans / restarts don't
    refetch, and the exit-time CSV row reads the same assessment made at entry.

No new pip dependencies: Google News RSS is parsed with stdlib ElementTree and
Gemini is called with the `requests` library already used elsewhere.

Output schema (assess_news → dict):
    news_signal   : SUPPORTS | CONTRADICTS | NEUTRAL | NO_NEWS | UNAVAILABLE
    news_score    : float -1.0..+1.0  (sign aligned so + = supports OUR direction)
    news_conf     : float 0.0..1.0    (classifier confidence)
    news_headline : str               (strongest relevant headline, truncated)
    news_count    : int               (# items found in the lookback window)
    news_source   : gemini | keyword | none
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from config.settings import (
    NEWS_CLASSIFIER, NEWS_LOOKBACK_HOURS, NEWS_MAX_ITEMS,
    NEWS_FETCH_TIMEOUT_SEC, NEWS_LLM_TIMEOUT_SEC, NEWS_SUPPORT_THRESHOLD,
    GEMINI_MODEL, NEWS_CACHE_DIR, UNIVERSE_FILE,
)

log = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_PATH)

_HEADLINE_MAXLEN = 120
_GNEWS_URL = "https://news.google.com/rss/search"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_UA = "Mozilla/5.0 (compatible; TradingAgentNewsBot/1.0)"

# Company-name suffixes to strip so the news query matches how the press writes it.
_NAME_SUFFIXES = re.compile(
    r"\b(LTD|LIMITED|LTD\.|CORP|CORPORATION|CO|COMPANY|INDIA|INDIAN|PVT|PRIVATE|"
    r"ENTERPRISES|INDUSTRIES|HOLDINGS|GROUP|&\s*CO)\b\.?",
    re.IGNORECASE,
)

# Minimal finance lexicon for the offline keyword fallback (used only when the
# LLM is unavailable or NEWS_CLASSIFIER="keyword"). Stock-bullishness sign.
_POS_WORDS = {
    "beats", "beat", "surge", "surges", "jumps", "rally", "record", "high",
    "upgrade", "upgraded", "outperform", "buy", "wins", "win", "order", "bags",
    "approval", "approved", "profit", "growth", "expansion", "buyback", "dividend",
    "strong", "gains", "gain", "soars", "rises", "raises", "guidance", "acquires",
}
_NEG_WORDS = {
    "miss", "misses", "plunge", "plunges", "slumps", "falls", "crash", "probe",
    "downgrade", "downgraded", "sell", "underperform", "fraud", "raid", "ban",
    "banned", "recall", "resign", "resigns", "default", "loss", "losses", "weak",
    "cuts", "cut", "warning", "warns", "lawsuit", "penalty", "fine", "scam", "slump",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────
def assess_news(symbol: str, company_name: str, direction, trade_date) -> dict:
    """
    Assess yesterday's/today's news for `symbol` relative to a `direction`
    (LONG/SHORT or +1/-1) trade. Never raises; returns a UNAVAILABLE dict on any
    failure. Cached per (trade_date, symbol).
    """
    dirn = _norm_direction(direction)
    try:
        cached = _load_cache(trade_date, symbol)
        if cached is not None:
            return cached
        result = _assess_impl(symbol, company_name, dirn)
        _save_cache(trade_date, symbol, result)
        return result
    except Exception as e:                      # noqa: BLE001 — must never propagate
        log.warning(f"news: assessment failed for {symbol} ({e}) — UNAVAILABLE")
        return _unavailable()


def _assess_impl(symbol: str, company_name: str, dirn: str) -> dict:
    query = _build_query(company_name, symbol)
    items = _fetch_headlines(query)
    if not items:
        return _result("NO_NEWS", 0.0, 0.0, "", 0, "none")

    titles = [it["title"] for it in items]
    strongest = titles[0]

    classifier = NEWS_CLASSIFIER
    if classifier == "off":
        return _result("NO_NEWS", 0.0, 0.0, "", len(items), "none")

    bullishness = conf = None
    source = "none"

    if classifier == "gemini":
        verdict = _classify_gemini(company_name, titles)
        if verdict is not None:
            bullishness = verdict["bullishness"]
            conf = verdict["confidence"]
            strongest = verdict.get("key_headline") or strongest
            source = "gemini"

    # keyword path: chosen explicitly, or as fallback when Gemini failed
    if bullishness is None:
        bullishness, conf, strongest = _classify_keyword(titles)
        source = "keyword"

    aligned = bullishness if dirn == "LONG" else -bullishness
    aligned = max(-1.0, min(1.0, aligned))
    conf = max(0.0, min(1.0, conf))

    if aligned > NEWS_SUPPORT_THRESHOLD:
        signal = "SUPPORTS"
    elif aligned < -NEWS_SUPPORT_THRESHOLD:
        signal = "CONTRADICTS"
    else:
        signal = "NEUTRAL"

    return _result(signal, round(aligned, 3), round(conf, 3),
                   _truncate(strongest), len(items), source)


# ─────────────────────────────────────────────────────────────────────────────
# Headline fetch (Google News RSS, stdlib XML parse)
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_headlines(query: str) -> list[dict]:
    """Return [{title, pubdate, source, link}] within the lookback window, newest first."""
    params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    url = f"{_GNEWS_URL}?{urllib.parse.urlencode(params)}"
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=NEWS_FETCH_TIMEOUT_SEC)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)

    items: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub_raw = item.findtext("pubDate")
        pub = _parse_pubdate(pub_raw)
        if pub is None or pub < cutoff:
            continue
        src_el = item.find("source")
        items.append({
            "title": title,
            "pubdate": pub,
            "source": (src_el.text or "").strip() if src_el is not None else "",
            "link": (item.findtext("link") or "").strip(),
        })

    items.sort(key=lambda it: it["pubdate"], reverse=True)
    return items[:NEWS_MAX_ITEMS]


def _parse_pubdate(raw: str | None):
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _build_query(company_name: str, symbol: str) -> str:
    clean = _NAME_SUFFIXES.sub("", company_name or "").strip()
    clean = re.sub(r"\s{2,}", " ", clean).strip(" &-")
    core = clean or symbol
    # Quoted phrase keeps the query tight; the context terms bias toward market news.
    return f'"{core}" (NSE OR share OR shares OR stock OR results)'


# ─────────────────────────────────────────────────────────────────────────────
# Classifier: Gemini Flash (REST, no SDK)
# ─────────────────────────────────────────────────────────────────────────────
def _classify_gemini(company_name: str, titles: list[str]) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("news: GEMINI_API_KEY missing — falling back to keyword classifier")
        return None

    headlines_block = "\n".join(f"- {t}" for t in titles)
    system = (
        "You are a financial news analyst for Indian equities listed on the NSE. "
        "You judge whether recent news is bullish or bearish for a specific stock "
        "over the current intraday session. Consider only material, price-relevant "
        "information (results, orders, upgrades/downgrades, regulatory action, "
        "management changes, guidance). Ignore generic market commentary and "
        "unrelated companies with similar names."
    )
    prompt = (
        f"Company: {company_name}\n\n"
        f"Recent headlines (most recent first):\n{headlines_block}\n\n"
        "Rate the news for THIS stock and respond with ONLY a JSON object:\n"
        '{"bullishness": <number -1.0..1.0, positive=bullish for the stock, '
        '0=neutral/none>, "confidence": <number 0.0..1.0>, '
        '"key_headline": "<the single most price-relevant headline verbatim>", '
        '"reason": "<one short sentence>"}'
    )

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 512,
            "responseMimeType": "application/json",
        },
    }
    url = _GEMINI_URL.format(model=GEMINI_MODEL)
    resp = requests.post(
        url, params={"key": api_key}, json=body, timeout=NEWS_LLM_TIMEOUT_SEC,
    )
    if resp.status_code != 200:
        log.warning(f"news: Gemini HTTP {resp.status_code}: {resp.text[:200]} — falling back")
        return None

    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(_strip_fences(text))
        return {
            "bullishness": float(data.get("bullishness", 0.0)),
            "confidence": float(data.get("confidence", 0.0)),
            "key_headline": str(data.get("key_headline", "")).strip(),
            "reason": str(data.get("reason", "")).strip(),
        }
    except Exception as e:                      # noqa: BLE001
        log.warning(f"news: could not parse Gemini response ({e}) — falling back")
        return None


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Classifier: offline keyword lexicon (fallback)
# ─────────────────────────────────────────────────────────────────────────────
def _classify_keyword(titles: list[str]) -> tuple[float, float, str]:
    best_title = titles[0]
    best_abs = 0.0
    net = 0
    hits = 0
    for t in titles:
        words = set(re.findall(r"[a-zA-Z]+", t.lower()))
        pos = len(words & _POS_WORDS)
        neg = len(words & _NEG_WORDS)
        score = pos - neg
        net += score
        if pos or neg:
            hits += 1
        if abs(score) > best_abs:
            best_abs = abs(score)
            best_title = t
    # Normalize the aggregate into [-1, 1]; confidence grows with signal density.
    bullishness = max(-1.0, min(1.0, net / 3.0))
    confidence = 0.0 if hits == 0 else min(0.6, 0.2 + 0.1 * hits)  # keyword is low-confidence by design
    return bullishness, confidence, best_title


# ─────────────────────────────────────────────────────────────────────────────
# Company-name lookup (tradingsymbol -> press-friendly name)
# ─────────────────────────────────────────────────────────────────────────────
_NAME_MAP: dict[str, str] | None = None


def company_name_for(symbol: str) -> str:
    """Map a tradingsymbol to its company name from config/universe.csv; falls back to the symbol."""
    global _NAME_MAP
    if _NAME_MAP is None:
        _NAME_MAP = _load_name_map()
    return _NAME_MAP.get(symbol, symbol)


def _load_name_map() -> dict[str, str]:
    try:
        import pandas as pd
        df = pd.read_csv(UNIVERSE_FILE, usecols=["tradingsymbol", "name"])
        return dict(zip(df["tradingsymbol"].astype(str), df["name"].astype(str)))
    except Exception as e:                      # noqa: BLE001
        log.warning(f"news: could not load company names from {UNIVERSE_FILE} ({e})")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Caching
# ─────────────────────────────────────────────────────────────────────────────
def _cache_path(trade_date, symbol: str) -> Path:
    return NEWS_CACHE_DIR / f"{trade_date}_{symbol}.json"


def _load_cache(trade_date, symbol: str) -> dict | None:
    path = _cache_path(trade_date, symbol)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save_cache(trade_date, symbol: str, result: dict) -> None:
    try:
        NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(trade_date, symbol).write_text(json.dumps(result))
    except Exception as e:                      # noqa: BLE001
        log.debug(f"news: could not cache result for {symbol} ({e})")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _norm_direction(direction) -> str:
    if isinstance(direction, (int, float)):
        return "LONG" if direction >= 0 else "SHORT"
    return "SHORT" if str(direction).upper().startswith("S") else "LONG"


def _truncate(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= _HEADLINE_MAXLEN else text[: _HEADLINE_MAXLEN - 1] + "…"


def _result(signal: str, score: float, conf: float,
            headline: str, count: int, source: str) -> dict:
    return {
        "news_signal": signal,
        "news_score": score,
        "news_conf": conf,
        "news_headline": headline,
        "news_count": count,
        "news_source": source,
    }


def _unavailable() -> dict:
    return _result("UNAVAILABLE", 0.0, 0.0, "", 0, "none")
