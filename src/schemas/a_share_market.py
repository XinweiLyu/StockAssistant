"""Typed market contracts; unknown upstream fields remain unknown."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def iso_day(value: str) -> str:
    return date.fromisoformat(value).isoformat()


def history_dates(start: str, end: str) -> tuple[str, str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    try:
        floor = b.replace(year=b.year-5)
    except ValueError:
        floor = b.replace(year=b.year-5, day=28)
    if a > b or a < floor:
        raise ValueError('历史期间须先后有序且不超过5年')
    return a.isoformat(), b.isoformat()


class MarketModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class MarketStock(MarketModel):
    code: str = Field(pattern=r'^(\d{6}|DEMO\d{3})$')
    name: str
    exchange: Literal['SSE','SZSE','BSE','unknown'] = 'unknown'
    board: Literal['main','growth','star','beijing','unknown'] = 'unknown'
    st: bool | None = None
    listed_date: str | None = None
    identity_verified: bool = False
    identity_conflict: bool = False
    source: str
    fetched_at: str


class MarketQuote(MarketModel):
    code: str
    name: str | None = None
    price: float | None = None
    change: float | None = None
    volume: float | None = Field(None, ge=0)
    amount: float | None = Field(None, ge=0)
    source: str
    source_time: str | None = None
    fetched_at: str
    trade_date: str | None = None
    suspended: bool | None = None
    limit_up: float | None = None
    limit_down: float | None = None


class MarketBar(MarketModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = Field(None, ge=0)
    amount: float | None = Field(None, ge=0)

    _date = field_validator('date')(iso_day)

    @model_validator(mode='after')
    def coherent(self):
        if self.low > min(self.open,self.close) or self.high < max(self.open,self.close) or self.low > self.high:
            raise ValueError('开高低收价不一致')
        return self


class SectorRecord(MarketModel):
    sector_id: str
    code: str
    name: str
    kind: Literal['industry','concept']
    classification: str
    source: str
    change: float | None = None
    amount: float | None = None
    up: int | None = None
    down: int | None = None
    flat: int | None = None
    unknown: int | None = None
    fetched_at: str
    source_time: str | None = None
    membership_version: str | None = None


class HistoryPage(MarketModel):
    code: str
    items: list[MarketBar] = Field(default_factory=list)
    warmup_items: list[MarketBar] = Field(default_factory=list)
    latest_change: float | None = None
    adjust: Literal['raw','qfq'] = 'raw'
    source: str | None = None
    adjustment_basis: str | None = None
    requested_start: str
    requested_end: str
    actual_start: str | None = None
    actual_end: str | None = None
    state: Literal['ready','partial','pending','failed','stale'] = 'pending'
    fetched_at: str | None = None
    task_id: str | None = None
    demo: bool = False
    limitations: list[str] = Field(default_factory=list)


class CatalogQuery(MarketModel):
    q: str = Field('', max_length=80)
    board: Literal['main','growth','star','beijing','unknown'] | None = None
    industry_id: str | None = Field(None,max_length=180)
    concept_id: str | None = Field(None,max_length=180)
    st: bool | None = None
    sort: Literal['change','amount','name','code'] = 'change'
    direction: Literal['asc','desc'] = 'desc'
    page: int = Field(1,ge=1)
    page_size: int = Field(50,ge=1,le=100)


class SectorQuery(MarketModel):
    kind: Literal['industry','concept'] = 'industry'
    classification: str | None = Field(None,max_length=80)
    period: Literal[0,5,20,60] = 0
