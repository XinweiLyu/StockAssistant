"""Versioned, source-bound evidence shared by integrated research roles."""
from __future__ import annotations

from datetime import datetime, date, time
import hashlib
import json
from typing import Any, Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field

TZ = ZoneInfo('Asia/Shanghai')
VERSION = 'integrated-research-v4'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def stamp(value, *, end_of_day=True):
    if value is None or str(value) in ('', 'None', 'nan', 'NaT'):
        return None
    text = str(value).strip().replace('Z', '+00:00')
    if len(text) == 8 and text.isdigit():
        text = f'{text[:4]}-{text[4:6]}-{text[6:]}'
    if len(text) == 10:
        day = date.fromisoformat(text)
        return datetime.combine(day, time(23, 59, 59) if end_of_day else time(), TZ).isoformat()
    parsed = datetime.fromisoformat(text)
    return (parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)).isoformat()


class ResearchFact(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    fact_id: str
    code: str = Field(pattern=r'^\d{6}$|^DEMO\d{3}$')
    category: str
    values: dict[str, Any]
    units: dict[str, str] = Field(default_factory=dict)
    source: str
    published_at: str | None = None
    observed_at: str
    available_at: str
    revised_at: str | None = None
    report_period: str | None = None
    report_type: str | None = None
    vintage_quality: str
    historical_eligible: bool = False
    url: str | None = None
    raw_fields: dict = Field(default_factory=dict)
    content_hash: str = ''


class ResearchBundle(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    version: str = VERSION
    code: str
    name: str
    cutoff: str
    anchor_date: str
    reference_price: float = Field(gt=0)
    source: str
    price_basis: str = 'raw'
    history_binding: dict
    data_hash: str
    facts: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    cases: dict = Field(default_factory=dict)
    baseline: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    coverage: list[dict] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    demo: bool = False


class IntegratedForecast(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    horizon_sessions: Literal[5, 20, 60]
    scenario: Literal['bear', 'base', 'bull']
    low: float = Field(gt=0, strict=True)
    high: float = Field(gt=0, strict=True)
    conditions: list[str] = Field(min_length=1, max_length=8)
    sources: list[str] = Field(min_length=1, max_length=24)
    basis_ids: list[str] = Field(min_length=1, max_length=8)
    derivation: str = Field(min_length=4, max_length=1600)


class SecondaryEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    low: float = Field(gt=0, strict=True)
    high: float = Field(gt=0, strict=True)
    conditions: list[str] = Field(min_length=1, max_length=8)
    invalidation: list[str] = Field(min_length=1, max_length=8)


class IntegratedPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    horizon_sessions: Literal[5,20,60]
    strategy_kind: Literal['trend_pullback','range_reversion','event_followthrough','observe']
    status: Literal['conditional','observe']
    entry_low: float | None = Field(None,gt=0,strict=True)
    entry_high: float | None = Field(None,gt=0,strict=True)
    stop_reference: float | None = Field(None,gt=0,strict=True)
    second_entry: SecondaryEntry | None = None
    targets: list[float] = Field(default_factory=list,max_length=3)
    conditions: list[str] = Field(min_length=1,max_length=8)
    invalidation: list[str] = Field(min_length=1,max_length=8)
    valid_until: str
    sources: list[str] = Field(min_length=1,max_length=24)
    basis_ids: list[str] = Field(min_length=1,max_length=8)
    derivation: str = Field(min_length=4,max_length=1600)
