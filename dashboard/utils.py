"""Formatting helpers and color constants shared across dashboard pages."""

RESULT_COLORS = {
    "EXACT_WIN": "#22c55e",   # green-500
    "WIN":       "#86efac",   # green-300
    "LOSS":      "#f87171",   # red-400
}

EXIT_COLORS = {
    "TARGET_HIT": "#22c55e",
    "TIME_EXIT":  "#facc15",
    "STOP_HIT":   "#f87171",
}

CONVICTION_COLORS = {
    "ULTRA":    "#a855f7",
    "HIGH":     "#3b82f6",
    "STANDARD": "#94a3b8",
}

WIN_RATE_COLOR_SCALE = [
    [0.0,  "#ef4444"],   # red   — <40%
    [0.40, "#f97316"],   # orange
    [0.55, "#facc15"],   # amber — 40–55%
    [0.70, "#22c55e"],   # green — ≥55%
    [1.0,  "#15803d"],   # deep green
]


def fmt_rs(x: float, show_sign: bool = True) -> str:
    if show_sign:
        return f"Rs {x:+,.0f}"
    return f"Rs {x:,.0f}"


def fmt_pct(x: float, decimals: int = 1) -> str:
    return f"{x:.{decimals}f}%"


def winrate_cell_color(wr: float) -> str:
    if wr >= 55:
        return "#16a34a"
    if wr >= 40:
        return "#ca8a04"
    return "#dc2626"
