"""The scenario grid used in notebook 05, section 9 (one place, so notebook and scripts agree)."""
from __future__ import annotations

from analysis.policies import ExitRule, LIVE_EXIT
from analysis.scenarios import Spec

NO_TRAIL = ExitRule(stop="cap1", target="strategy", trail=False)
FIXED_1_1 = ExitRule(stop="fixed:1.0", target="fixed:1.0", trail=False)      # the owner's +1% / -1% plan
FIXED_09_1 = ExitRule(stop="fixed:1.0", target="fixed:0.9", trail=False)

drift_le = lambda x: (lambda c: c.drift_dec < x)      # causal drift (bar-B open)
drift_ge = lambda x: (lambda c: c.drift_dec >= x)
nifty_ge = lambda x: (lambda c: c.nifty_now_pct >= x)
not_fc = lambda c: c.driver != "FIRST-CANDLE"
agree_ge = lambda n: (lambda c: c.agreeing >= n)          # votes cast SO FAR (causal)
after = lambda hhmm: (lambda c: c.scan >= hhmm)
AND = lambda *fs: (lambda c: __import__("functools").reduce(lambda a, b: a & b, [f(c) for f in fs]))

SPECS = [
    # ── A. what live does, and the owner's question about skipping ──────────────────
    Spec("A1 live rules (all gates), live exits", select="live"),
    Spec("A2 first-pass stock, market, live exits"),
    Spec("A3 first-pass stock, LIMIT at level 30m, live exits", entry="limit", limit_bars=6),
    Spec("A4 first-pass stock, LIMIT at level 60m, live exits", entry="limit", limit_bars=12),
    # ── B. the drift gate, both directions ──────────────────────────────────────────
    Spec("B1 first-pass, drift < 0.3% (live's gate only)", mask=drift_le(0.3)),
    Spec("B2 first-pass, drift >= 0.3% (inverted gate)", mask=drift_ge(0.3)),
    Spec("B3 first-pass, drift >= 0.5%", mask=drift_ge(0.5)),
    # ── C. market filter ────────────────────────────────────────────────────────────
    Spec("C1 first-pass, NIFTY >= +0.2% vs open", mask=nifty_ge(0.2)),
    Spec("C2 first-pass, NIFTY >= 0 vs open", mask=nifty_ge(0.0)),
    Spec("C3 inverted gate + NIFTY >= +0.2%", mask=AND(drift_ge(0.3), nifty_ge(0.2))),
    Spec("C4 live rules + NIFTY >= +0.2%", select="live", mask=nifty_ge(0.2)),
    # ── D. driver ───────────────────────────────────────────────────────────────────
    Spec("D1 first-pass, no FIRST-CANDLE driver", mask=not_fc),
    Spec("D2 inverted gate + NIFTY>=0.2 + no FIRST-CANDLE", mask=AND(drift_ge(0.3), nifty_ge(0.2), not_fc)),
    # ── E. exits on the main candidates ─────────────────────────────────────────────
    Spec("E1 first-pass, no trailing lock", exit=NO_TRAIL),
    Spec("E2 first-pass, fixed +1% / -1%", exit=FIXED_1_1),
    Spec("E3 first-pass, fixed +0.9% / -1%", exit=FIXED_09_1),
    Spec("E4 inverted gate + NIFTY>=0.2, no trail", mask=AND(drift_ge(0.3), nifty_ge(0.2)), exit=NO_TRAIL),
    Spec("E5 inverted gate + NIFTY>=0.2, fixed +1%/-1%", mask=AND(drift_ge(0.3), nifty_ge(0.2)), exit=FIXED_1_1),
    Spec("E6 live rules, fixed +1% / -1%", select="live", exit=FIXED_1_1),
    # ── T. timing: skip the opening minutes ────────────────────────────────────────
    Spec("T1 first-pass, scans from 09:35 (skip first 20 min)", mask=after("09:35")),
    Spec("T2 first-pass, scans from 09:50", mask=after("09:50")),
    Spec("T3 live rules, scans from 09:35", select="live", mask=after("09:35")),
    # ── F. wait for agreement to build (the backtest's edge came from votes that arrive later) ──
    Spec("F1 first candidate with >=7 agreeing so far", mask=agree_ge(7)),
    Spec("F2 first candidate with >=9 agreeing so far", mask=agree_ge(9)),
    Spec("F3 >=7 agreeing + NIFTY >= 0", mask=AND(agree_ge(7), nifty_ge(0.0))),
    Spec("F4 >=9 agreeing + NIFTY >= 0", mask=AND(agree_ge(9), nifty_ge(0.0))),
]
