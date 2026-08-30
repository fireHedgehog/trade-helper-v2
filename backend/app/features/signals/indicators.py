"""Indicator primitives (docs/draft-design/04-trend-page.md §R1).

Pure Python over `list[float]`, oldest -> newest, same style as
`multisectional/ranking.py`. Every series returned is the same length as the
input, with `None` where the window is not yet full.
"""

from __future__ import annotations

Num = float | None


def wilder_atr(high: list[float], low: list[float], close: list[float], n: int) -> list[Num]:
    """Wilder's ATR. `TR_t` uses `close_{t-1}`; seeded with the SMA of the
    first `n` true ranges, then `ATR_t = ATR_{t-1} + (TR_t - ATR_{t-1})/n`."""
    length = len(close)
    tr: list[float] = [high[0] - low[0]]
    for t in range(1, length):
        tr.append(max(
            high[t] - low[t],
            abs(high[t] - close[t - 1]),
            abs(low[t] - close[t - 1]),
        ))
    out: list[Num] = [None] * length
    if length < n:
        return out
    seed = sum(tr[:n]) / n
    out[n - 1] = seed
    prev = seed
    for t in range(n, length):
        prev = prev + (tr[t] - prev) / n
        out[t] = prev
    return out


def donchian(values_hi: list[float], values_lo: list[float], n: int) -> tuple[list[Num], list[Num]]:
    """Channel over the **prior** `n` bars (current bar excluded — you cannot
    break out of a level that already contains your own bar, §R0). Returns
    `(upper, lower)`; both `None` until `n` prior bars exist."""
    length = len(values_hi)
    up: list[Num] = [None] * length
    dn: list[Num] = [None] * length
    for t in range(n, length):
        up[t] = max(values_hi[t - n:t])
        dn[t] = min(values_lo[t - n:t])
    return up, dn


def sma(values: list[float], n: int) -> list[Num]:
    length = len(values)
    out: list[Num] = [None] * length
    if length < n:
        return out
    window = sum(values[:n])
    out[n - 1] = window / n
    for t in range(n, length):
        window += values[t] - values[t - n]
        out[t] = window / n
    return out


def ema(values: list[float], n: int) -> list[Num]:
    length = len(values)
    out: list[Num] = [None] * length
    if length < n:
        return out
    alpha = 2.0 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for t in range(n, length):
        prev = alpha * values[t] + (1 - alpha) * prev
        out[t] = prev
    return out


def rolling_max(values: list[float], n: int) -> list[Num]:
    length = len(values)
    out: list[Num] = [None] * length
    for t in range(length):
        if t + 1 >= n:
            out[t] = max(values[t + 1 - n:t + 1])
    return out


def rolling_min(values: list[float], n: int) -> list[Num]:
    length = len(values)
    out: list[Num] = [None] * length
    for t in range(length):
        if t + 1 >= n:
            out[t] = min(values[t + 1 - n:t + 1])
    return out


def confirmed_pivots(
    high: list[float], low: list[float], k: int = 3
) -> tuple[list[int], list[int]]:
    """Indices of confirmed swing highs / lows. A pivot at `i` needs `high_i`
    strictly above the `k` bars before and `>=` the `k` bars after; it is only
    *known* at `i + k` (no lookahead). Mirrored for lows."""
    length = len(high)
    highs: list[int] = []
    lows: list[int] = []
    for i in range(k, length - k):
        win_before_h = high[i - k:i]
        win_after_h = high[i + 1:i + 1 + k]
        if high[i] > max(win_before_h) and high[i] >= max(win_after_h):
            highs.append(i)
        win_before_l = low[i - k:i]
        win_after_l = low[i + 1:i + 1 + k]
        if low[i] < min(win_before_l) and low[i] <= min(win_after_l):
            lows.append(i)
    return highs, lows
