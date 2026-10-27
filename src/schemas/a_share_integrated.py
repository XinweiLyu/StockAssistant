"""Versioned, source-bound evidence shared by integrated research roles."""
from __future__ import annotations

from datetime import datetime, date, time
import hashlib
import json
import re
from typing import Any, Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator

TZ = ZoneInfo('Asia/Shanghai')
VERSION = 'integrated-research-v6'


def canonical_plan_day(value):
    """Accept a real calendar day only in the persisted YYYY-MM-DD format."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('计划有效日期须为YYYY-MM-DD格式')
    return date.fromisoformat(value).isoformat()


def earnings_stage(title):
    """Separate earnings statements from conferences and other administrative notices."""
    title = re.sub(r'\s+', '', title)
    # Dates, publication schedules and investor meetings discuss a statement;
    # they do not constitute a new statement, even if a report is in the title.
    statement = r'(?:20\d{2}年)?(?:(?:半年度|年度|第?[一二三四]季度|中期)报告|(?:半年度|年度|第?[一二三四]季度|中期)?业绩(?:预告|快报))(?:及其?摘要|摘要)?'
    timing_action = r'(?:延期|延迟|推迟|暂缓|预约)'
    schedule = (rf'{timing_action}披露|披露(?:延期|延迟|推迟|暂缓|预约|时间|日期|日程|安排|计划|日)'
                rf'|{timing_action}(?:公司)?《?{statement}》?的?披露|{statement}的?{timing_action}')
    meeting = (r'业绩(?:网上|网络|线上|线下|集体)*(?:说明会|交流会)'
               r'|投资者(?:说明会|交流(?:会|活动)?|沟通(?:会|活动)?|接待日|关系活动|见面会)')
    if re.search(schedule, title) or re.search(meeting, title):
        return 0
    if any(w in title for w in ('预告', '预增', '预减', '预盈', '预亏')):
        return 1
    if '快报' in title:
        return 2
    if any(w in title for w in ('年度报告', '季度报告', '中期报告')):
        return 3
    return 0


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

    @field_validator('valid_until', mode='before')
    @classmethod
    def valid_plan_day(cls, value):
        return canonical_plan_day(value)
