"""
Top-10 correlation-reduced strategy backtest (2021-2026).

Independent of backtester/engine.py — separate capital model (own Rs 10L per
strategy, Rs 5L long / Rs 5L short, max 1 long + 1 short trade per strategy per
day), separate universe rules (LONG: >=Rs 300cr turnover, SHORT: F&O list only).
Reuses only the pure data/mechanics helpers from backtester/engine.py and
backtester/cost_model.py that have nothing to do with the old composite-scoring
system.
"""
