"""A-share cost distribution estimate from unadjusted daily OHLC and turnover.

The 150-bin decay/triangle model follows the public AkShare/Eastmoney CYQ
calculation. It is an estimate of tradable cost distribution, not exchange
holdings or a vendor-published chip snapshot.
"""
from __future__ import annotations

from datetime import date
from math import ceil, floor, isfinite
from typing import Mapping, Sequence

from .realtime_types import ChipDistribution


def calculate_chip_distribution(
    stock_code: str, rows: Sequence[Mapping[str, object]]
) -> ChipDistribution | None:
    """Calculate the latest chip estimate only when daily inputs are complete."""
    bars = []
    seen_dates = set()
    for row in rows:
        if str(row.get("tradestatus", "1")) != "1":
            continue
        try:
            day = date.fromisoformat(str(row["date"])[:10])
            prices = [float(row[key]) for key in ("open", "high", "low", "close")]
            turnover = float(row["turn"])
        except (KeyError, TypeError, ValueError):
            return None
        if (day in seen_dates or not all(isfinite(p) and p > 0 for p in prices)
                or not isfinite(turnover) or turnover < 0
                or prices[2] > min(prices) or prices[1] < max(prices)):
            return None
        seen_dates.add(day)
        bars.append((day, *prices, turnover))
    bars.sort(key=lambda bar: bar[0])
    bars = bars[-210:]
    if len(bars) < 90:
        return None

    minimum = min(bar[3] for bar in bars)
    maximum = max(bar[2] for bar in bars)
    step = max(0.01, (maximum - minimum) / 149)
    chips = [0.0] * 150
    for _, opened, high, low, closed, turnover in bars:
        rate = min(1.0, turnover / 100.0)
        if rate == 0:
            continue
        chips = [value * (1 - rate) for value in chips]
        mean = (opened + high + low + closed) / 4
        centre = max(0, min(149, floor((mean - minimum) / step)))
        if high == low:
            chips[centre] += 149 * rate / 2
            continue
        apex = 2 / (high - low)
        start = max(0, ceil((low - minimum) / step))
        stop = min(149, floor((high - minimum) / step))
        for index in range(start, stop + 1):
            price = minimum + step * index
            if price <= mean:
                weight = apex if abs(mean - low) < 1e-8 else (price - low) / (mean - low) * apex
            else:
                weight = apex if abs(high - mean) < 1e-8 else (high - price) / (high - mean) * apex
            chips[index] += max(0.0, weight) * rate

    total = sum(chips)
    if not isfinite(total) or total <= 0:
        return None

    def cost(share: float) -> float:
        target = total * share
        accumulated = 0.0
        for index, value in enumerate(chips):
            accumulated += value
            if accumulated > target:
                return minimum + index * step
        return minimum + 149 * step

    def interval(share: float) -> tuple[float, float, float]:
        lower = cost((1 - share) / 2)
        upper = cost((1 + share) / 2)
        concentration = (upper - lower) / (upper + lower) if upper + lower else 0.0
        return round(lower, 2), round(upper, 2), concentration

    low90, high90, concentration90 = interval(0.9)
    low70, high70, concentration70 = interval(0.7)
    close = bars[-1][4]
    profitable = sum(value for index, value in enumerate(chips)
                     if close >= minimum + index * step)
    return ChipDistribution(
        code=stock_code,
        date=bars[-1][0].isoformat(),
        source="baostock/estimated_cyq",
        profit_ratio=min(1.0, max(0.0, profitable / total)),
        avg_cost=round(cost(0.5), 2),
        cost_90_low=low90,
        cost_90_high=high90,
        concentration_90=concentration90,
        cost_70_low=low70,
        cost_70_high=high70,
        concentration_70=concentration70,
    )
