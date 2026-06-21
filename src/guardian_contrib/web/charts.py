"""Server-rendered SVG charts for the Public Ledger — editorial style, CSS-animated
(line-draw, bars grow), JS hover tooltips. No chart library. Returns SVG strings
(used with Jinja's |safe). Colors come from CSS classes (ch-*) where possible so
they stay on-theme; segment fills use the shared palette inline."""
from __future__ import annotations

import datetime as dt

from .format import fmt_compact, fmt_money

PALETTE = ["#1f4a3d", "#8d2a1b", "#9c6f1f", "#2f6354", "#b0884a", "#837a68"]
_W = 720


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _empty(msg: str = "No itemized contributions on record.") -> str:
    return f'<p class="chart-empty">{_esc(msg)}</p>'


def line_chart(series, height: int = 178) -> str:
    """series: [(date_iso, cumulative_cents)]. Featured 'money over time' chart."""
    if not series or len(series) < 2:
        return _empty()
    pl, pr, pt, pb = 10, 12, 16, 24
    dates = [dt.date.fromisoformat(d) for d, _ in series]
    d0, d1 = dates[0], dates[-1]
    span = max(1, (d1 - d0).days)
    vmax = max(v for _, v in series) or 1

    def X(d):
        return pl + (_W - pl - pr) * ((d - d0).days / span)

    def Y(v):
        return pt + (height - pt - pb) * (1 - v / vmax)

    pts = [(X(d), Y(v)) for d, (_, v) in zip(dates, series)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"M{pts[0][0]:.1f},{height - pb:.1f} L"
            + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            + f" L{pts[-1][0]:.1f},{height - pb:.1f} Z")
    dots = "".join(
        f'<circle class="ch-dot" cx="{x:.1f}" cy="{y:.1f}" r="3.2" '
        f'data-tip="{_esc(series[i][0])} · {_esc(fmt_money(series[i][1]))}"/>'
        for i, (x, y) in enumerate(pts))
    return (
        f'<svg class="chart" viewBox="0 0 {_W} {height}" role="img" '
        f'aria-label="Cumulative contributions over time">'
        f'<path class="ch-area" d="{area}"/><path class="ch-line" d="{line}"/>{dots}'
        f'<text class="ch-ax" x="{pl}" y="{height - 7}">{_esc(d0.isoformat())}</text>'
        f'<text class="ch-ax" x="{_W - pr}" y="{height - 7}" text-anchor="end">{_esc(d1.isoformat())}</text>'
        f'<text class="ch-ax" x="{pl}" y="12">{_esc(fmt_compact(vmax))}</text></svg>')


def hbar_chart(items, label_chars: int = 28) -> str:
    """items: [(label, cents)] — horizontal bars (top donors / race comparison)."""
    items = [(l, c) for l, c in items if c]
    if not items:
        return _empty("No data.")
    vmax = max(c for _, c in items) or 1
    rowh, labelw, valw = 30, 188, 96
    barx = labelw + 8
    barw = _W - barx - valw
    h = rowh * len(items) + 6
    rows = []
    for i, (name, cents) in enumerate(items):
        y = i * rowh + 4
        w = max(2.0, barw * (cents / vmax))
        rows.append(
            f'<text class="ch-lbl" x="0" y="{y + rowh * 0.64:.0f}">{_esc(str(name)[:label_chars])}</text>'
            f'<rect class="ch-bar" x="{barx}" y="{y + 5:.0f}" width="{w:.1f}" height="{rowh - 13}" '
            f'rx="3" style="animation-delay:{i * 55}ms" '
            f'data-tip="{_esc(name)} · {_esc(fmt_money(cents))}"/>'
            f'<text class="ch-val" x="{barx + w + 7:.1f}" y="{y + rowh * 0.64:.0f}">{_esc(fmt_money(cents))}</text>')
    return (f'<svg class="chart" viewBox="0 0 {_W} {h}" role="img" '
            f'aria-label="Ranked bar chart">{"".join(rows)}</svg>')


def segmented_bar(segments) -> str:
    """segments: [(label, cents)] — one stacked bar + legend (funding sources)."""
    segments = [(l, c) for l, c in segments if c > 0]
    if not segments:
        return _empty("No data.")
    total = sum(c for _, c in segments) or 1
    barH = 38
    h = barH + len(segments) * 24 + 14
    x = 0.0
    segs, legend = [], []
    for i, (label, cents) in enumerate(segments):
        w = _W * (cents / total)
        pct = round(cents * 100 / total)
        color = PALETTE[i % len(PALETTE)]
        segs.append(
            f'<rect class="ch-seg" x="{x:.1f}" y="0" width="{w:.1f}" height="{barH}" '
            f'fill="{color}" style="animation-delay:{i * 90}ms" '
            f'data-tip="{_esc(label)} · {_esc(fmt_money(cents))} ({pct}%)"/>')
        ly = barH + 20 + i * 24
        legend.append(
            f'<rect x="0" y="{ly - 11}" width="12" height="12" rx="2.5" fill="{color}"/>'
            f'<text class="ch-lbl" x="20" y="{ly}">{_esc(label)}</text>'
            f'<text class="ch-val" x="{_W}" y="{ly}" text-anchor="end">{_esc(fmt_money(cents))} · {pct}%</text>')
        x += w
    return (f'<svg class="chart" viewBox="0 0 {_W} {h}" role="img" '
            f'aria-label="Funding sources breakdown">'
            f'<g class="ch-segs">{"".join(segs)}</g>{"".join(legend)}</svg>')


def register(env) -> None:
    env.globals["line_chart"] = line_chart
    env.globals["hbar_chart"] = hbar_chart
    env.globals["segmented_bar"] = segmented_bar
