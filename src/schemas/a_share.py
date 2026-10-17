"""Local assistant configuration; secrets stay in the existing environment config."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    stock_cap: float = Field(.10, gt=0, le=1)
    sector_cap: float = Field(.20, gt=0, le=1)
    total_cap: float = Field(.60, gt=0, le=1)
    risk_per_trade: float = Field(.005, gt=0, le=.05)
    commission: float = Field(.0003, ge=0, le=.02)
    minimum_fee: float = Field(5., ge=0, le=100)
    transfer_fee: float = Field(.00001, ge=0, le=.02)


class AssistantSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    mode: Literal['demo', 'free', 'tushare2000', 'tushare5000'] = 'demo'
    research_scope: Literal['limited', 'all'] = 'all'
    pool_size: int = Field(40, ge=30, le=200)
    watchlist: list[str] = Field(default_factory=list, max_length=50)
    account_id: int | None = Field(None, gt=0)
    snapshot_provider: Literal['akshare', 'tushare'] = 'akshare'
    realtime_entitled: bool = False
    news_entitled: bool = False
    announcements_entitled: bool = False
    free_fallback: bool = True
    research_enabled: bool = False
    model: str = ''
    daily_model_calls: int = Field(20, ge=0, le=20)
    risk: RiskSettings = Field(default_factory=RiskSettings)

    @field_validator('watchlist')
    @classmethod
    def valid_codes(cls, value):
        if any(len(c) != 6 or not c.isdigit() for c in value):
            raise ValueError('自选股必须是6位股票代码')
        return list(dict.fromkeys(value))


class VerifyEvent(BaseModel):
    major_risk: bool
    note: str = Field(min_length=2, max_length=1000)
    code: str = Field(pattern=r'^\d{6}$|^DEMO\d{3}$')


class HoldingConstraint(BaseModel):
    code: str = Field(pattern=r'^\d{6}$|^DEMO\d{3}$')
    sellable: int | None = Field(None, ge=0)
    stop: float | None = Field(None, gt=0, allow_inf_nan=False)
    note: str = Field(min_length=2, max_length=1000)
