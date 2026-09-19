"""
How faithfully does the causal replay reproduce what live actually did?

Three levels, from the live session logs (analysis.live_log_parser):
  1. inputs  : for every candidate live logged in its top-3 (score / agreeing at a scan), does the
               replay have the same stock at the same scan with the same score and agreement?
  2. gates   : for every drift / viability skip live logged, does the replay reach the same verdict?
  3. picks   : does the replay take the same stock live took that day?
Level 1 tests the signals and votes; level 2 adds the price model; level 3 is the end result,
which is hypersensitive to a few paisa (a 0.2% price difference can flip the viability gate).
"""
from __future__ import annotations

import pandas as pd


def validate(cand: pd.DataFrame, dec: pd.DataFrame) -> dict:
    c = cand.copy()
    c["key"] = list(zip(c.date, c.scan, c.symbol))
    rec = c.drop_duplicates("key").set_index("key").to_dict("index")      # key -> row dict
    out = {}

    top = dec[(dec.event == "TOP") & (dec.get("dir") == "LONG") & dec.agreeing.notna()]
    top = top[top.date.isin(c.date.unique()) & (top.scan_slot <= c.scan.max())]
    k = list(zip(top.date, top.scan_slot, top.sym))
    found = [x in rec for x in k]
    m = top[found].copy()
    kk = list(zip(m.date, m.scan_slot, m.sym))
    m["r_score"] = [rec[x]["raw_score"] for x in kk]
    m["r_agree"] = [rec[x]["agreeing"] for x in kk]
    m["r_qok"] = [rec[x]["quality_ok"] for x in kk]
    out["inputs"] = dict(
        logged_top_candidates=len(top),
        found_in_replay_same_scan=int(sum(found)),
        score_exact=round(100 * ((m.score - m.r_score).abs() < 0.01).mean(), 1),
        agreeing_exact=round(100 * (m.agreeing == m.r_agree).mean(), 1),
        pass_fail_same=round(100 * ((m.verdict == "PASS") == (m.r_qok == True)).mean(), 1),
    )

    sk = dec[dec.event.isin(["SKIP_DRIFT", "SKIP_VIABILITY"]) & (dec.get("dir") == "LONG")]
    sk = sk[sk.date.isin(c.date.unique()) & (sk.scan_slot <= c.scan.max())]
    ks = list(zip(sk.date, sk.scan_slot, sk.sym))
    have = [x in rec for x in ks]
    s = sk[have].copy()
    kk = list(zip(s.date, s.scan_slot, s.sym))
    s["r_gate"] = [rec[x]["gate_c"] for x in kk]
    s["r_drift"] = [rec[x]["drift_dec"] for x in kk]
    s["r_level"] = [rec[x]["level"] for x in kk]
    s["same_gate"] = s.event == s.r_gate
    s["any_skip"] = s.r_gate.isin(["SKIP_DRIFT", "SKIP_VIABILITY", "SKIP_DEAD", "SKIP_RR"])
    lvl = s[s.event == "SKIP_DRIFT"]
    out["gates"] = dict(
        logged_skips=len(sk), found=int(sum(have)),
        same_gate_pct=round(100 * s.same_gate.mean(), 1),
        skipped_either_way_pct=round(100 * s.any_skip.mean(), 1),
        level_exact_pct=round(100 * ((lvl.entry - lvl.r_level).abs() / lvl.entry < 1e-3).mean(), 1),
        drift_abs_err_median=round((lvl.drift - lvl.r_drift).abs().median(), 3),
    )

    sig = dec[(dec.event == "SIGNAL") & (dec.get("dir") == "LONG") & dec.date.isin(c.date.unique())]
    take = c[c.live_take_c == True].groupby("date").head(1).set_index("date")
    rows = []
    for r in sig.itertuples():
        t = take.loc[r.date] if r.date in take.index else None
        qp = c[(c.date == r.date) & (c.symbol == r.sym) & (c.quality_ok == True)]
        rows.append(dict(date=r.date, live=r.sym, live_scan=r.scan_slot,
                         replay=None if t is None else t.symbol, replay_scan=None if t is None else t.scan,
                         live_stock_passed_quality_in_replay=len(qp) > 0))
    P = pd.DataFrame(rows)
    out["picks"] = dict(days=len(P), same_stock_pct=round(100 * (P.live == P.replay).mean(), 1),
                        live_stock_quality_pass_in_replay_pct=round(100 * P.live_stock_passed_quality_in_replay.mean(), 1))
    out["pick_table"] = P
    out["skip_table"] = s
    return out
